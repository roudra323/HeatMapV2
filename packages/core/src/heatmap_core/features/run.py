"""Compute and store behaviour snapshots for every synced, tracked wallet."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import polars as pl
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import WalletFeatureSnapshot
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import hub_addresses
from heatmap_core.features.context import SIDES_SCHEMA, WALLETS_SCHEMA, FeatureContext
from heatmap_core.features.registry import FEATURE_VERSION, compute_all
from heatmap_core.graph.expansion import high_degree_addresses
from heatmap_core.logging import get_logger
from heatmap_core.primitives import NATIVE_TOKEN, NULL_ADDRESS, AddressKind

log = get_logger(__name__)

TRACKED_SQL = text(
    """
    SELECT w.address
    FROM watchlist w
    JOIN sync_cursors c ON c.chain_id = w.chain_id AND c.address = w.address
    WHERE w.chain_id = :chain_id AND w.active AND c.last_block > 0
    """
)

TRANSFERS_SQL = text(
    """
    SELECT t.tx_hash, t.block_time, t.category, t.from_address, t.to_address,
           t.token_address, t.amount_usd::float8 AS amount_usd, (t.raw_amount = 0) AS is_zero,
           COALESCE(tok.category, 'other') AS token_category
    FROM transfers t
    LEFT JOIN tokens tok ON tok.chain_id = t.chain_id AND tok.address = t.token_address
    WHERE t.chain_id = :chain_id
      AND NOT t.is_spam
      AND t.normalized_at IS NOT NULL
      AND t.block_time <= :snapshot_at
      AND (t.from_address = ANY(:wallets) OR t.to_address = ANY(:wallets))
    """
)

WALLETS_SQL = text(
    """
    SELECT w.address AS wallet, w.funded_by, wc.community_id
    FROM wallets w
    LEFT JOIN wallet_communities wc ON wc.chain_id = w.chain_id AND wc.address = w.address
    WHERE w.chain_id = :chain_id AND w.address = ANY(:wallets)
    """
)


@dataclass
class FeatureRunResult:
    snapshot_at: datetime
    rows: int = 0
    wallets_by_window: dict[str, int] = field(default_factory=dict)
    skipped: bool = False


def load_context(
    engine: Engine, chain: Chain, settings: Settings, snapshot_at: datetime
) -> FeatureContext:
    """Transfers of synced, tracked wallets, as one row per (wallet, transfer side).

    Tracked wallets that turned out to be hubs (labelled, or more distinct
    counterparties than ``expansion.hub_degree_threshold``) are left out: they
    are exchanges, payout or treasury wallets, not people, and one of them can
    hold millions of transfers.
    """
    chain_id = chain.chain_id
    busy = high_degree_addresses(engine, chain_id, settings.expansion.hub_degree_threshold)
    with session_scope(engine) as session:
        hubs = hub_addresses(session, chain_id) | {NULL_ADDRESS, NATIVE_TOKEN} | busy
        tracked = [a for a in session.scalars(TRACKED_SQL, {"chain_id": chain_id}) if a not in hubs]
        params = {"chain_id": chain_id, "wallets": tracked, "snapshot_at": snapshot_at}
        transfers = session.execute(TRANSFERS_SQL, params).mappings().all()
        wallet_rows = session.execute(WALLETS_SQL, params).mappings().all()
        entities: dict[str, str] = {
            address: category
            for address, category in session.execute(
                text("SELECT address, category FROM entity_labels WHERE chain_id = :chain_id"),
                {"chain_id": chain_id},
            )
        }
        contracts = set(
            session.scalars(
                text("SELECT address FROM wallets WHERE chain_id = :chain_id AND kind = :kind"),
                {"chain_id": chain_id, "kind": AddressKind.CONTRACT.value},
            )
        )

    tracked_set = set(tracked)
    wallet_records = [
        {**dict(r), "funder_is_hub": r["funded_by"] in hubs if r["funded_by"] else None}
        for r in wallet_rows
    ]
    sides: list[dict[str, Any]] = []
    for t in transfers:
        for wallet, cp, direction in (
            (t["from_address"], t["to_address"], "out"),
            (t["to_address"], t["from_address"], "in"),
        ):
            if wallet not in tracked_set or wallet == cp:
                continue
            sides.append(
                {
                    "wallet": wallet,
                    "direction": direction,
                    "counterparty": cp,
                    "tx_hash": t["tx_hash"],
                    "block_time": t["block_time"],
                    "category": t["category"],
                    "token_address": t["token_address"],
                    "token_category": t["token_category"],
                    "amount_usd": t["amount_usd"],
                    "is_zero": t["is_zero"],
                    "cp_entity": entities.get(cp),
                    "cp_is_hub": cp in hubs,
                    "cp_is_contract": cp in contracts,
                    "cp_tracked": cp in tracked_set,
                }
            )
    return FeatureContext(
        sides=pl.DataFrame(sides, schema=SIDES_SCHEMA),
        wallets=pl.DataFrame(wallet_records, schema=WALLETS_SCHEMA),
        snapshot_at=snapshot_at,
        window="all",
        co_timing_seconds=settings.features.co_timing_seconds,
    )


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 8)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def compute_features(
    engine: Engine, chain: Chain, settings: Settings, *, snapshot_at: datetime | None = None
) -> FeatureRunResult:
    snapshot_at = (snapshot_at or datetime.now(UTC)).replace(microsecond=0)
    base = load_context(engine, chain, settings, snapshot_at)
    result = FeatureRunResult(snapshot_at=snapshot_at)

    rows: list[dict[str, Any]] = []
    for window in settings.features.windows:
        ctx = base.for_window(window)
        if ctx.sides.is_empty():
            result.wallets_by_window[window] = 0
            continue
        frame = compute_all(ctx).filter(pl.col("transfer_count") >= settings.features.min_transfers)
        result.wallets_by_window[window] = frame.height
        for record in frame.iter_rows(named=True):
            wallet = record.pop("wallet")
            features = {k: _clean(v) for k, v in record.items()}
            rows.append(
                {
                    "chain_id": chain.chain_id,
                    "address": wallet,
                    "window": window,
                    "snapshot_at": snapshot_at,
                    "feature_version": FEATURE_VERSION,
                    "transfer_count": int(record["transfer_count"]),
                    "volume_usd": features.get("volume_usd"),
                    "features": features,
                }
            )

    with session_scope(engine) as session:
        session.execute(
            delete(WalletFeatureSnapshot).where(
                WalletFeatureSnapshot.chain_id == chain.chain_id,
                WalletFeatureSnapshot.snapshot_at == snapshot_at,
            )
        )
        for start in range(0, len(rows), 1000):
            session.execute(insert(WalletFeatureSnapshot).values(rows[start : start + 1000]))
    result.rows = len(rows)
    log.info(
        "features.done",
        chain=chain.name,
        snapshot_at=snapshot_at.isoformat(),
        rows=result.rows,
        **{f"wallets_{w}": n for w, n in result.wallets_by_window.items()},
    )
    return result


def latest_snapshot_at(engine: Engine, chain_id: int) -> datetime | None:
    with session_scope(engine) as session:
        return session.scalar(
            select(WalletFeatureSnapshot.snapshot_at)
            .where(WalletFeatureSnapshot.chain_id == chain_id)
            .order_by(WalletFeatureSnapshot.snapshot_at.desc())
            .limit(1)
        )
