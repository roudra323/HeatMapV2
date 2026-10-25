"""Per-trader statistics over recent trades, bot verdicts, and promotion to the watchlist.

Each transaction is routed one of three ways, judged by the contract the
signer called (``tx_to``):

- ``settlement``: an intent/solver settlement (CoW, UniswapX). The signer is a
  solver or filler, not the person trading.
- ``router``: a labelled router, or a contract that many distinct signers call
  a few times each (aggregators and trading bots used by real people).
- ``private``: the pool itself, the v4 PoolManager, or any other contract,
  e.g. one called by a few signers, or by a handful of rotating signers that
  each trade constantly. This is how MEV and arbitrage bots trade.

A signer is also a bot when most of its transactions are circular (every token
it sold it also bought back: arbitrage), or when it packs many swaps into each
transaction (a solver or market maker settling other people's orders).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.config import Chain, Settings
from heatmap_core.config.settings import DiscoveryConfig
from heatmap_core.db.models import DexTrader, EntityLabel, WatchlistEntry
from heatmap_core.db.session import insert_batches, session_scope
from heatmap_core.dex.valuation import quote_tokens
from heatmap_core.logging import get_logger
from heatmap_core.primitives import NATIVE_TOKEN, WatchOrigin

log = get_logger(__name__)

RECENT = """
    WITH recent AS (
        SELECT t.*
        FROM dex_trades t
        JOIN dex_pools p ON p.chain_id = t.chain_id AND p.pool_id = t.pool_id AND p.verified
        WHERE t.chain_id = :chain_id AND t.block_time >= :since
    )
"""

STATS_SQL = text(
    RECENT
    + """
    , callees AS (
        SELECT
            tx_to,
            COUNT(DISTINCT trader) AS signers,
            COUNT(DISTINCT tx_hash)::float8 / COUNT(DISTINCT trader) AS txs_per_signer
        FROM recent
        GROUP BY tx_to
    ), txs AS (
        SELECT
            r.trader,
            r.tx_hash,
            MIN(r.block_time) AS at,
            MAX(r.amount_usd) AS usd,  -- multi-hop swaps: count the transaction once
            COUNT(*) AS swaps,
            COUNT(*) > 1
                AND array_agg(DISTINCT r.token_in) <@ array_agg(DISTINCT r.token_out)
                AND array_agg(DISTINCT r.token_out) <@ array_agg(DISTINCT r.token_in) AS cyclic,
            CASE
                WHEN bool_or(el.category = 'settlement') THEN 'settlement'
                WHEN bool_or(r.tx_to IS NULL OR r.tx_to = r.pool_id OR r.tx_to = :pool_manager)
                    THEN 'private'
                WHEN bool_or(el.category = 'dex_router') THEN 'router'
                WHEN MAX(c.signers) >= :min_router_signers
                    AND MAX(c.txs_per_signer) <= :max_router_txs_per_signer THEN 'router'
                ELSE 'private'
            END AS route
        FROM recent r
        LEFT JOIN callees c ON c.tx_to = r.tx_to
        LEFT JOIN entity_labels el ON el.chain_id = r.chain_id AND el.address = r.tx_to
        GROUP BY r.trader, r.tx_hash
    )
    SELECT
        trader,
        MIN(at) AS first_trade_at,
        MAX(at) AS last_trade_at,
        COUNT(*) AS tx_count,
        COUNT(DISTINCT (at AT TIME ZONE 'UTC')::date) AS active_days,
        SUM(usd) AS volume_usd,
        MAX(usd) AS max_tx_usd,
        AVG((route = 'router')::int)::float8 AS router_share,
        AVG((route = 'private')::int)::float8 AS private_share,
        AVG((route = 'settlement')::int)::float8 AS settlement_share,
        AVG(swaps)::float8 AS swaps_per_tx,
        AVG(cyclic::int)::float8 AS arbitrage_share
    FROM txs
    GROUP BY trader
    """
)

TOKENS_SQL = text(
    RECENT
    + """
    , sides AS (
        SELECT trader, token_in AS token FROM recent
        UNION ALL
        SELECT trader, token_out FROM recent
    ), counts AS (
        SELECT trader, token, COUNT(*) AS trades FROM sides GROUP BY trader, token
    ), ranked AS (
        SELECT
            c.*,
            ROW_NUMBER() OVER (
                PARTITION BY trader
                ORDER BY (token = ANY(:quotes)), trades DESC, token
            ) AS rank
        FROM counts c
    )
    SELECT r.trader, r.token, r.trades, r.rank, tok.symbol
    FROM ranked r
    LEFT JOIN tokens tok ON tok.chain_id = :chain_id AND tok.address = r.token
    """
)

PROTOCOLS_SQL = text(
    RECENT + "SELECT trader, array_agg(DISTINCT protocol) FROM recent GROUP BY trader"
)

TOP_TOKENS = 5
# Trading five different tokens already marks an active trader; more should not
# outrank volume, or wallets dumping dozens of airdrops come first.
RANK_TOKENS_CAP = 5


@dataclass
class TraderStats:
    traders: int = 0
    bots: int = 0


def bot_reason(row: Any, cfg: DiscoveryConfig) -> str | None:
    if row.settlement_share >= 0.5:
        return "settlement_signer"
    if row.private_share >= 0.5:
        return "private_contract"
    if row.arbitrage_share >= cfg.bot_arbitrage_share:
        return "arbitrage"
    if row.swaps_per_tx >= cfg.bot_swaps_per_tx:
        return "batch_executor"
    if row.tx_count / max(row.active_days, 1) >= cfg.bot_tx_per_day:
        return "high_frequency"
    return None


def refresh_traders(
    engine: Engine, chain: Chain, settings: Settings, *, now: datetime | None = None
) -> TraderStats:
    """Recompute ``dex_traders`` from verified-pool trades in the discovery window."""
    cfg = settings.discovery
    now = now or datetime.now(UTC)
    # Stablecoins and ETH are what people pay with, not what they are trading.
    quote_map, stable = quote_tokens(engine, chain)
    wrapped = chain.config.wrapped_native
    quotes = sorted({*quote_map, NATIVE_TOKEN, *filter(None, [wrapped])})
    params = {
        "chain_id": chain.chain_id,
        "since": now - timedelta(days=cfg.window_days),
        "pool_manager": (chain.config.uniswap_v4_pool_manager or "").lower(),
        "min_router_signers": cfg.min_router_signers,
        "max_router_txs_per_signer": cfg.max_router_txs_per_signer,
        "quotes": quotes,
    }
    with session_scope(engine) as session:
        stats = session.execute(STATS_SQL, params).all()
        tokens: dict[str, list[Any]] = defaultdict(list)
        distinct: dict[str, int] = defaultdict(int)
        traded: dict[str, set[str]] = defaultdict(set)  # besides stablecoins; WETH is ETH
        for r in session.execute(TOKENS_SQL, params):
            distinct[r.trader] += 1
            if r.token not in stable:
                traded[r.trader].add(NATIVE_TOKEN if r.token == wrapped else r.token)
            if r.rank <= TOP_TOKENS:
                tokens[r.trader].append({"token": r.token, "symbol": r.symbol, "trades": r.trades})
        protocols: dict[str, list[str]] = dict(
            session.execute(PROTOCOLS_SQL, params).tuples().all()
        )

    result = TraderStats()
    rows = []
    for r in stats:
        reason = bot_reason(r, cfg)
        result.bots += int(reason is not None)
        rows.append(
            {
                "chain_id": chain.chain_id,
                "address": r.trader,
                "first_trade_at": r.first_trade_at,
                "last_trade_at": r.last_trade_at,
                "tx_count": r.tx_count,
                "active_days": r.active_days,
                "volume_usd": r.volume_usd,
                "max_tx_usd": r.max_tx_usd,
                "distinct_tokens": distinct[r.trader],
                "traded_tokens": len(traded[r.trader]),
                "protocols": sorted(protocols.get(r.trader) or []),
                "top_tokens": tokens[r.trader],
                "router_share": r.router_share,
                "private_share": r.private_share,
                "settlement_share": r.settlement_share,
                "swaps_per_tx": r.swaps_per_tx,
                "arbitrage_share": r.arbitrage_share,
                "is_bot": reason is not None,
                "bot_reason": reason,
                "computed_at": now,
            }
        )
    with session_scope(engine) as session:
        session.execute(delete(DexTrader).where(DexTrader.chain_id == chain.chain_id))
        for batch in insert_batches(rows):
            session.execute(insert(DexTrader).values(batch))
    result.traders = len(rows)
    log.info("dex.traders_done", chain=chain.name, traders=result.traders, bots=result.bots)
    return result


def promote_traders(engine: Engine, chain: Chain, settings: Settings) -> list[str]:
    """Add the steadiest, most varied human-looking traders to the watchlist, within the caps.

    Candidates are ranked by active days, then by how many tokens they trade
    besides stablecoins (up to ``RANK_TOKENS_CAP``), then by volume. Ranking by
    volume alone fills the watchlist with treasuries and stablecoin rebalancers.
    Every wallet ever placed on the watchlist is skipped, so traders the sync
    vetting rejected, or that were removed by hand, are never promoted again;
    they do not count towards ``max_total`` either.
    """
    cfg = settings.discovery.promote
    if not cfg.enabled:
        return []
    chain_id = chain.chain_id
    with session_scope(engine) as session:
        tracked = (
            session.scalar(
                select(func.count())
                .select_from(WatchlistEntry)
                .where(
                    WatchlistEntry.chain_id == chain_id,
                    WatchlistEntry.origin == WatchOrigin.TRADER,
                    WatchlistEntry.active.is_(True),
                )
            )
            or 0
        )
        room = min(cfg.max_per_run, cfg.max_total - tracked)
        if room <= 0:
            return []
        watched = select(WatchlistEntry.address).where(WatchlistEntry.chain_id == chain_id)
        # Only labelled hubs can sign transactions; tokens and pools are contracts.
        hubs = select(EntityLabel.address).where(
            EntityLabel.chain_id == chain_id, EntityLabel.is_hub.is_(True)
        )
        chosen = session.scalars(
            select(DexTrader)
            .where(
                DexTrader.chain_id == chain_id,
                DexTrader.is_bot.is_(False),
                DexTrader.volume_usd >= cfg.min_volume_usd,
                DexTrader.tx_count >= cfg.min_trades,
                DexTrader.active_days >= cfg.min_active_days,
                DexTrader.address.not_in(watched),
                DexTrader.address.not_in(hubs),
            )
            .order_by(
                DexTrader.active_days.desc(),
                func.least(DexTrader.traded_tokens, RANK_TOKENS_CAP).desc(),
                DexTrader.volume_usd.desc(),
                DexTrader.address,
            )
            .limit(room)
        ).all()
        if chosen:
            window = settings.discovery.window_days
            session.execute(
                insert(WatchlistEntry)
                .values(
                    [
                        {
                            "chain_id": chain_id,
                            "address": t.address,
                            "origin": WatchOrigin.TRADER,
                            "hop": 0,
                            "priority": 100,
                            "active": True,
                            "note": f"DEX trader: ${t.volume_usd:,.0f} in {t.tx_count} txs, "
                            f"{t.traded_tokens} tokens, over {window}d",
                        }
                        for t in chosen
                    ]
                )
                .on_conflict_do_nothing()
            )
    addresses = [t.address for t in chosen]
    log.info("dex.promoted", chain=chain.name, count=len(addresses))
    return addresses
