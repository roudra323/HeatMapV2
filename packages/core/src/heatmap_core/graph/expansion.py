"""Neighbour discovery: grow the watchlist from seeds without crossing hubs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import WatchlistEntry
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import hub_addresses
from heatmap_core.logging import get_logger
from heatmap_core.primitives import NATIVE_TOKEN, NULL_ADDRESS, WatchOrigin

log = get_logger(__name__)

COUNTERPARTY_SQL = text(
    """
    SELECT wallet, counterparty, COUNT(*) AS interactions, COALESCE(SUM(amount_usd), 0) AS usd
    FROM (
        SELECT from_address AS wallet, to_address AS counterparty, amount_usd
        FROM transfers
        WHERE chain_id = :chain_id AND from_address = ANY(:wallets)
          AND NOT is_spam AND block_time >= :since
        UNION ALL
        SELECT to_address, from_address, amount_usd
        FROM transfers
        WHERE chain_id = :chain_id AND to_address = ANY(:wallets)
          AND NOT is_spam AND block_time >= :since
    ) AS sides
    WHERE wallet <> counterparty
    GROUP BY wallet, counterparty
    HAVING COUNT(*) >= :min_interactions
    """
)


@dataclass
class ExpansionResult:
    added: list[str] = field(default_factory=list)
    skipped_hubs: set[str] = field(default_factory=set)
    capped: bool = False


def high_degree_addresses(engine: Engine, chain_id: int, threshold: int) -> set[str]:
    """Addresses with more distinct counterparties than ``threshold`` in the edge table."""
    query = text(
        """
        SELECT address FROM (
            SELECT src AS address, dst AS other FROM edges WHERE chain_id = :chain_id
            UNION
            SELECT dst, src FROM edges WHERE chain_id = :chain_id
        ) AS pairs
        GROUP BY address
        HAVING COUNT(*) > :threshold
        """
    )
    with session_scope(engine) as session:
        return set(session.scalars(query, {"chain_id": chain_id, "threshold": threshold}).all())


def expand_neighbours(
    engine: Engine, chain: Chain, settings: Settings, *, now: datetime | None = None
) -> ExpansionResult:
    """Add the strongest non-hub counterparties of watched wallets to the watchlist.

    Runs one hop per call: wallets at hop ``h < max_hops`` contribute neighbours
    at hop ``h + 1``. Neighbours added now are synced by the next sync run and
    can expand further on the next expansion run.
    """
    cfg = settings.expansion
    result = ExpansionResult()
    if not cfg.enabled or cfg.max_hops == 0:
        return result

    chain_id = chain.chain_id
    since = (now or datetime.now(UTC)) - timedelta(days=cfg.window_days)

    with session_scope(engine) as session:
        hubs = hub_addresses(session, chain_id) | {NULL_ADDRESS, NATIVE_TOKEN}
        watch = {
            e.address: e
            for e in session.scalars(
                select(WatchlistEntry).where(WatchlistEntry.chain_id == chain_id)
            )
        }
        neighbour_count = (
            session.scalar(
                select(func.count())
                .select_from(WatchlistEntry)
                .where(
                    WatchlistEntry.chain_id == chain_id,
                    WatchlistEntry.origin == WatchOrigin.NEIGHBOUR,
                )
            )
            or 0
        )
    hubs |= high_degree_addresses(engine, chain_id, cfg.hub_degree_threshold)

    frontier = [
        e for e in watch.values() if e.active and e.hop < cfg.max_hops and e.address not in hubs
    ]
    if not frontier:
        return result

    with session_scope(engine) as session:
        rows = session.execute(
            COUNTERPARTY_SQL,
            {
                "chain_id": chain_id,
                "wallets": [e.address for e in frontier],
                "since": since,
                "min_interactions": cfg.min_interactions,
            },
        ).all()

    ranked: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
    for wallet, counterparty, interactions, usd in rows:
        ranked[wallet].append((counterparty, int(interactions), float(usd)))

    budget = cfg.max_total_neighbours - neighbour_count
    new_rows: list[dict[str, object]] = []
    # Seeds and lower hops first, then by priority, so the budget goes to the closest wallets.
    for parent in sorted(frontier, key=lambda e: (e.hop, e.priority, e.address)):
        candidates = sorted(ranked.get(parent.address, []), key=lambda c: (-c[1], -c[2], c[0]))
        taken = 0
        for counterparty, _, _ in candidates:
            if taken >= cfg.top_n_per_wallet:
                break
            if counterparty in hubs:
                result.skipped_hubs.add(counterparty)
                continue
            if counterparty in watch:
                continue
            if budget <= 0:
                result.capped = True
                break
            hop = parent.hop + 1
            new_rows.append(
                {
                    "chain_id": chain_id,
                    "address": counterparty,
                    "origin": WatchOrigin.NEIGHBOUR,
                    "hop": hop,
                    "via_address": parent.address,
                    "priority": 100 + 10 * hop,
                    "active": True,
                }
            )
            watch[counterparty] = WatchlistEntry(address=counterparty, hop=hop)
            result.added.append(counterparty)
            budget -= 1
            taken += 1

    if new_rows:
        with session_scope(engine) as session:
            session.execute(insert(WatchlistEntry).values(new_rows).on_conflict_do_nothing())

    log.info(
        "expansion.done",
        chain=chain.name,
        added=len(result.added),
        skipped_hubs=len(result.skipped_hubs),
        capped=result.capped,
    )
    return result
