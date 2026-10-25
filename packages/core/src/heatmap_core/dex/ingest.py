"""Scan new blocks for DEX swaps and store them as trades by the transaction signer.

The trader is ``tx.from``: the Swap event's own ``sender`` is usually a router
or aggregator contract. Logs are read in ``discovery.logs_block_range`` windows
(the Alchemy free tier allows 10 blocks per ``eth_getLogs``) and each window
commits with the cursor, so a failed run resumes where it stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import DexCursor, DexTrade, Token
from heatmap_core.db.session import session_scope
from heatmap_core.dex.abi import ContractReader
from heatmap_core.dex.events import SWAP_TOPICS, SwapLog, parse_swap_log, trade_sides
from heatmap_core.dex.pools import Factory, ensure_pools, load_factories
from heatmap_core.logging import get_logger

log = get_logger(__name__)

# Numeric(78, 18) holds 60 integer digits; absurd amounts of junk tokens are left unscaled.
MAX_AMOUNT = Decimal(10) ** 59
INSERT_BATCH = 2000


class DexSource(ContractReader, Protocol):
    """What trade discovery needs from the provider layer (``ProviderRouter`` implements it)."""

    def latest_block(self, chain: Chain) -> int: ...

    def get_logs(
        self, chain: Chain, from_block: int, to_block: int, topics: list[Any]
    ) -> list[dict[str, Any]]: ...

    def get_block(self, chain: Chain, number: int) -> dict[str, Any]: ...


@dataclass
class IngestResult:
    from_block: int = 0
    to_block: int = 0
    swaps: int = 0
    trades: int = 0
    unresolved: int = 0


def scaled(raw: int, decimals: int | None) -> Decimal | None:
    if decimals is None:
        return None
    value = Decimal(raw).scaleb(-decimals)
    return value if value < MAX_AMOUNT else None


def ingest_swaps(
    engine: Engine, source: DexSource, chain: Chain, settings: Settings, *, head: int | None = None
) -> IngestResult:
    cfg = settings.discovery
    if head is None:
        head = source.latest_block(chain)
    safe_head = head - chain.config.confirmations
    with session_scope(engine) as session:
        cursor = session.get(DexCursor, chain.chain_id)
        if cursor is not None:
            start = cursor.last_block + 1
        else:
            start = max(chain.config.start_block, safe_head - cfg.backfill_blocks + 1)
    end = min(safe_head, start + cfg.max_blocks_per_run - 1)
    result = IngestResult(from_block=start, to_block=end)
    if start > end:
        return result

    factories = load_factories(chain)
    manager = chain.config.uniswap_v4_pool_manager
    for window_start in range(start, end + 1, cfg.logs_block_range):
        window_end = min(end, window_start + cfg.logs_block_range - 1)
        logs = source.get_logs(chain, window_start, window_end, [SWAP_TOPICS])
        swaps = [s for entry in logs if (s := parse_swap_log(entry, manager)) is not None]
        rows = _trade_rows(engine, source, chain, factories, swaps, result) if swaps else []
        with session_scope(engine) as session:
            for i in range(0, len(rows), INSERT_BATCH):
                stmt = (
                    insert(DexTrade)
                    .values(rows[i : i + INSERT_BATCH])
                    .on_conflict_do_nothing(index_elements=["chain_id", "tx_hash", "log_index"])
                    .returning(DexTrade.id)
                )
                result.trades += len(session.execute(stmt).all())
            cursor_row = insert(DexCursor).values(chain_id=chain.chain_id, last_block=window_end)
            session.execute(
                cursor_row.on_conflict_do_update(
                    index_elements=["chain_id"], set_={"last_block": cursor_row.excluded.last_block}
                )
            )
        result.swaps += len(swaps)

    log.info("dex.ingest_done", chain=chain.name, **result.__dict__)
    return result


def _trade_rows(
    engine: Engine,
    source: DexSource,
    chain: Chain,
    factories: dict[str, Factory],
    swaps: list[SwapLog],
    result: IngestResult,
) -> list[dict[str, Any]]:
    with session_scope(engine) as session:
        pools = ensure_pools(session, source, chain, {s.pool_id: s.kind for s in swaps}, factories)
        tokens = {t for p in pools.values() for t in (p.token0, p.token1) if t is not None}
        decimals = dict(
            session.execute(
                select(Token.address, Token.decimals).where(
                    Token.chain_id == chain.chain_id, Token.address.in_(tokens)
                )
            )
            .tuples()
            .all()
        )

    times: dict[int, datetime] = {}
    txs: dict[str, dict[str, Any]] = {}
    for number in sorted({s.block_number for s in swaps}):
        block = source.get_block(chain, number)
        times[number] = datetime.fromtimestamp(int(block["timestamp"], 16), tz=UTC)
        for tx in block.get("transactions") or []:
            if isinstance(tx, dict):
                txs[str(tx["hash"]).lower()] = tx

    rows: list[dict[str, Any]] = []
    for swap in swaps:
        pool = pools.get(swap.pool_id)
        tx = txs.get(swap.tx_hash)
        if pool is None or pool.token0 is None or pool.token1 is None or tx is None:
            result.unresolved += 1
            continue
        sides = trade_sides(swap.delta0, swap.delta1, pool.token0, pool.token1)
        if sides is None:
            continue
        token_in, raw_in, token_out, raw_out = sides
        rows.append(
            {
                "chain_id": chain.chain_id,
                "block_number": swap.block_number,
                "block_time": times[swap.block_number],
                "tx_hash": swap.tx_hash,
                "log_index": swap.log_index,
                "pool_id": swap.pool_id,
                "protocol": pool.protocol,
                "trader": str(tx["from"]).lower(),
                "tx_to": str(tx["to"]).lower() if tx.get("to") else None,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in_raw": Decimal(raw_in),
                "amount_out_raw": Decimal(raw_out),
                "amount_in": scaled(raw_in, decimals.get(token_in)),
                "amount_out": scaled(raw_out, decimals.get(token_out)),
            }
        )
    return rows
