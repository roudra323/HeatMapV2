"""Checks on wallets the pipeline adds by itself, before their first sync.

DEX traders and neighbours join the watchlist automatically. Some of them are
contracts (pools, vaults, routers) or exchange, payout and bot wallets that
have sent hundreds of thousands of transactions: syncing one takes hours, and
none of them is a person. Each automatically added wallet is checked once,
with ``eth_getCode`` and ``eth_getTransactionCount``; one that fails is
deactivated, with the reason in its watchlist note. Wallets added by hand are
never checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.config import Chain
from heatmap_core.config.settings import TrackingConfig
from heatmap_core.db.models import Wallet, WatchlistEntry
from heatmap_core.db.session import insert_batches, session_scope
from heatmap_core.ingestion.sync import TransferSource, kind_from_code
from heatmap_core.logging import get_logger
from heatmap_core.primitives import AddressKind, WatchOrigin
from heatmap_core.providers.errors import ProviderError

log = get_logger(__name__)

AUTOMATIC = (WatchOrigin.TRADER, WatchOrigin.NEIGHBOUR)


@dataclass
class VettingResult:
    checked: int = 0
    rejected: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def unvetted_addresses(session: Session, chain_id: int) -> list[str]:
    """Active, automatically added wallets that have not been checked yet."""
    query = (
        select(WatchlistEntry.address)
        .outerjoin(
            Wallet,
            (Wallet.chain_id == WatchlistEntry.chain_id)
            & (Wallet.address == WatchlistEntry.address),
        )
        .where(
            WatchlistEntry.chain_id == chain_id,
            WatchlistEntry.active.is_(True),
            WatchlistEntry.origin.in_(AUTOMATIC),
            Wallet.sent_txs.is_(None),
        )
        .order_by(WatchlistEntry.priority, WatchlistEntry.hop, WatchlistEntry.address)
    )
    return list(session.scalars(query))


def rejection(kind: AddressKind, sent_txs: int | None, cfg: TrackingConfig) -> str | None:
    if kind == AddressKind.CONTRACT:
        return "a contract, not a wallet"
    if sent_txs is not None and sent_txs > cfg.max_sent_txs:
        return f"sent {sent_txs:,} transactions (exchange, service or bot)"
    return None


def vet_new_wallets(
    engine: Engine, source: TransferSource, chain: Chain, cfg: TrackingConfig
) -> VettingResult:
    """Check every unvetted automatic wallet; deactivate the ones that are not people.

    A provider failure stops the checks; what was checked is kept and the rest
    waits for the next run (callers must not sync wallets still unvetted).
    """
    with session_scope(engine) as session:
        pending = unvetted_addresses(session, chain.chain_id)
    result = VettingResult()
    checked: dict[str, tuple[AddressKind, int | None]] = {}
    try:
        for address in pending:
            kind = kind_from_code(source.get_code(chain, address))
            sent = source.get_transaction_count(chain, address) if kind == AddressKind.EOA else None
            checked[address] = (kind, sent)
    except ProviderError as exc:
        log.warning("vetting.stopped", error=str(exc))
        result.error = str(exc)
    if not checked:
        return result

    rows = [
        {"chain_id": chain.chain_id, "address": a, "kind": kind, "sent_txs": sent}
        for a, (kind, sent) in checked.items()
    ]
    result.checked = len(rows)
    result.rejected = {
        a: reason for a, (kind, sent) in checked.items() if (reason := rejection(kind, sent, cfg))
    }
    with session_scope(engine) as session:
        for batch in insert_batches(rows):
            stmt = insert(Wallet).values(batch)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["chain_id", "address"],
                    set_={"kind": stmt.excluded.kind, "sent_txs": stmt.excluded.sent_txs},
                )
            )
        for address, reason in result.rejected.items():
            session.execute(
                update(WatchlistEntry)
                .where(WatchlistEntry.chain_id == chain.chain_id, WatchlistEntry.address == address)
                .values(
                    active=False,
                    note=func.concat_ws(" · ", WatchlistEntry.note, f"Not tracked: {reason}"),
                )
            )
    log.info(
        "vetting.done",
        chain=chain.name,
        checked=result.checked,
        rejected=len(result.rejected),
        waiting=len(pending) - result.checked,
    )
    return result
