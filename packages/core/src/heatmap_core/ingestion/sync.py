"""Incremental, idempotent ingestion of a wallet's transfers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import Engine, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.config import Chain
from heatmap_core.db.models import SyncCursor, Token, Transfer, Wallet
from heatmap_core.db.session import session_scope
from heatmap_core.logging import get_logger
from heatmap_core.primitives import AddressKind, TransferCategory, normalize_address
from heatmap_core.providers.base import RawTransfer

log = get_logger(__name__)
INSERT_BATCH = 2000


class TransferSource(Protocol):
    """What ingestion needs from the provider layer (``ProviderRouter`` implements it)."""

    def fetch_transfers(
        self, chain: Chain, address: str, from_block: int, to_block: int
    ) -> list[RawTransfer]: ...

    def latest_block(self, chain: Chain) -> int: ...

    def get_code(self, chain: Chain, address: str) -> str: ...


@dataclass
class SyncResult:
    address: str
    from_block: int
    to_block: int
    fetched: int = 0
    inserted: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)


def scaled_amount(raw: int | Decimal, decimals: int | None) -> Decimal | None:
    if decimals is None:
        return None
    return Decimal(raw).scaleb(-decimals)


def _token_standard(category: TransferCategory) -> str:
    return "native" if category.is_native else category.value


def _upsert_tokens(session: Any, chain_id: int, transfers: list[RawTransfer]) -> None:
    tokens: dict[str, dict[str, Any]] = {}
    for t in transfers:
        tokens.setdefault(
            t.token_address,
            {
                "chain_id": chain_id,
                "address": t.token_address,
                "standard": _token_standard(t.category),
                "symbol": (t.symbol or None) and t.symbol[:64],
                "name": (t.token_name or None) and t.token_name[:256],
                "decimals": t.decimals,
                "category": "nft" if t.category.is_nft else "other",
            },
        )
    if not tokens:
        return
    stmt = insert(Token).values(list(tokens.values()))
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["chain_id", "address"],
            # Fill gaps only; never overwrite verified metadata.
            set_={
                "symbol": func.coalesce(Token.symbol, stmt.excluded.symbol),
                "name": func.coalesce(Token.name, stmt.excluded.name),
                "decimals": func.coalesce(Token.decimals, stmt.excluded.decimals),
            },
        )
    )


def _upsert_wallets(session: Any, chain_id: int, transfers: list[RawTransfer]) -> None:
    seen: dict[str, tuple[datetime, datetime]] = {}
    for t in transfers:
        for address in (t.from_address, t.to_address):
            first, last = seen.get(address, (t.block_time, t.block_time))
            seen[address] = (min(first, t.block_time), max(last, t.block_time))
    if not seen:
        return
    rows = [
        {"chain_id": chain_id, "address": a, "first_seen_at": f, "last_seen_at": last}
        for a, (f, last) in seen.items()
    ]
    for start in range(0, len(rows), INSERT_BATCH):
        stmt = insert(Wallet).values(rows[start : start + INSERT_BATCH])
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["chain_id", "address"],
                set_={
                    "first_seen_at": func.least(Wallet.first_seen_at, stmt.excluded.first_seen_at),
                    "last_seen_at": func.greatest(Wallet.last_seen_at, stmt.excluded.last_seen_at),
                },
            )
        )


def _insert_transfers(session: Any, chain_id: int, transfers: list[RawTransfer]) -> int:
    inserted = 0
    rows = [
        {
            "chain_id": chain_id,
            "uid": t.uid,
            "tx_hash": t.tx_hash,
            "block_number": t.block_number,
            "block_time": t.block_time,
            "category": t.category.value,
            "from_address": t.from_address,
            "to_address": t.to_address,
            "token_address": t.token_address,
            "token_id": t.token_id[:80] if t.token_id else None,
            "raw_amount": Decimal(t.raw_amount),
            "amount": scaled_amount(t.raw_amount, t.decimals),
            "log_index": t.log_index,
            "provider": t.provider,
            "is_spam": False,
        }
        for t in transfers
    ]
    for start in range(0, len(rows), INSERT_BATCH):
        stmt = (
            insert(Transfer)
            .values(rows[start : start + INSERT_BATCH])
            .on_conflict_do_nothing(index_elements=["chain_id", "uid"])
            .returning(Transfer.id)
        )
        inserted += len(session.execute(stmt).all())
    return inserted


def sync_wallet(
    engine: Engine,
    source: TransferSource,
    chain: Chain,
    address: str,
    *,
    head: int | None = None,
) -> SyncResult:
    """Fetch new transfers for ``address`` up to the confirmed head.

    The last ``reorg_window`` blocks before the cursor are fetched again; stored
    transfers in that range which the provider no longer returns are deleted.
    Each block chunk commits together with the cursor, so a crash resumes
    where it stopped and re-runs never duplicate rows.
    """
    address = normalize_address(address)
    cfg = chain.config
    if head is None:
        head = source.latest_block(chain)
    safe_head = head - cfg.confirmations

    with session_scope(engine) as session:
        cursor = session.get(SyncCursor, (chain.chain_id, address))
        last_block = cursor.last_block if cursor else 0

    if last_block > 0:
        start = max(cfg.start_block, last_block - cfg.reorg_window + 1)
    else:
        start = cfg.start_block
    result = SyncResult(address=address, from_block=start, to_block=safe_head)
    if start > safe_head:
        return result

    reorg_until = last_block  # blocks <= this were stored before and may be stale
    chunk_start = start
    while chunk_start <= safe_head:
        chunk_end = min(chunk_start + cfg.sync_block_chunk - 1, safe_head)
        transfers = source.fetch_transfers(chain, address, chunk_start, chunk_end)
        result.fetched += len(transfers)

        with session_scope(engine) as session:
            if chunk_start <= reorg_until:
                result.removed += _remove_stale(
                    session,
                    chain.chain_id,
                    address,
                    chunk_start,
                    min(chunk_end, reorg_until),
                    {t.uid for t in transfers},
                )
            _upsert_tokens(session, chain.chain_id, transfers)
            _upsert_wallets(session, chain.chain_id, transfers)
            result.inserted += _insert_transfers(session, chain.chain_id, transfers)
            stmt = insert(SyncCursor).values(
                chain_id=chain.chain_id,
                address=address,
                last_block=chunk_end,
                last_synced_at=datetime.now(UTC),
                last_error=None,
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["chain_id", "address"],
                    set_={
                        "last_block": stmt.excluded.last_block,
                        "last_synced_at": stmt.excluded.last_synced_at,
                        "last_error": None,
                    },
                )
            )
        chunk_start = chunk_end + 1

    log.info(
        "sync.wallet_done",
        address=address,
        from_block=start,
        to_block=safe_head,
        fetched=result.fetched,
        inserted=result.inserted,
        removed=result.removed,
    )
    return result


def _remove_stale(
    session: Any, chain_id: int, address: str, from_block: int, to_block: int, keep: set[str]
) -> int:
    stmt = delete(Transfer).where(
        Transfer.chain_id == chain_id,
        or_(Transfer.from_address == address, Transfer.to_address == address),
        Transfer.block_number.between(from_block, to_block),
    )
    if keep:
        stmt = stmt.where(Transfer.uid.not_in(keep))
    return int(session.execute(stmt).rowcount or 0)


def record_sync_error(engine: Engine, chain: Chain, address: str, error: str) -> None:
    with session_scope(engine) as session:
        stmt = insert(SyncCursor).values(
            chain_id=chain.chain_id, address=address, last_block=0, last_error=error[:2000]
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["chain_id", "address"], set_={"last_error": error[:2000]}
            )
        )


def classify_addresses(
    engine: Engine, source: TransferSource, chain: Chain, addresses: list[str]
) -> dict[str, AddressKind]:
    """Mark addresses whose kind is unknown as EOA or contract via ``eth_getCode``."""
    with session_scope(engine) as session:
        unknown = list(
            session.scalars(
                select(Wallet.address).where(
                    Wallet.chain_id == chain.chain_id,
                    Wallet.address.in_(addresses),
                    Wallet.kind == AddressKind.UNKNOWN,
                )
            )
        )
        known_missing = set(addresses) - set(
            session.scalars(
                select(Wallet.address).where(
                    Wallet.chain_id == chain.chain_id, Wallet.address.in_(addresses)
                )
            )
        )
    kinds: dict[str, AddressKind] = {}
    for address in [*unknown, *sorted(known_missing)]:
        code = source.get_code(chain, address)
        kinds[address] = AddressKind.EOA if code in ("0x", "0x0", "") else AddressKind.CONTRACT
    if kinds:
        with session_scope(engine) as session:
            stmt = insert(Wallet).values(
                [{"chain_id": chain.chain_id, "address": a, "kind": k} for a, k in kinds.items()]
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["chain_id", "address"], set_={"kind": stmt.excluded.kind}
                )
            )
    return kinds
