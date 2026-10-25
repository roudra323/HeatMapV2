"""Stage functions shared by Dagster assets, the CLI and tests.

Each stage reads its inputs from the database and writes its outputs back,
so stages can run independently and on their own schedules. A stage holds a
PostgreSQL advisory lock per chain while it runs; a second run of the same
stage (an overlapping schedule, the sensor, the CLI) is skipped, not doubled.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text

from heatmap_core.config import Chain, Settings
from heatmap_core.config.settings import TrackingConfig
from heatmap_core.db.session import session_scope
from heatmap_core.dex.ingest import DexSource, IngestResult, ingest_swaps
from heatmap_core.dex.traders import promote_traders, refresh_traders
from heatmap_core.dex.valuation import value_trades
from heatmap_core.entities.labels import load_seed_labels, load_seed_tokens
from heatmap_core.features.run import FeatureRunResult, compute_features
from heatmap_core.graph.communities import detect_communities
from heatmap_core.graph.edges import rebuild_edges
from heatmap_core.graph.expansion import (
    ExpansionResult,
    expand_neighbours,
    high_degree_addresses,
)
from heatmap_core.ingestion.sync import (
    TransferSource,
    classify_addresses,
    classify_counterparties,
    record_sync_error,
    sync_wallet,
)
from heatmap_core.ingestion.vetting import unvetted_addresses, vet_new_wallets
from heatmap_core.ingestion.watchlist import active_addresses, unsynced_addresses
from heatmap_core.logging import get_logger
from heatmap_core.models.run import ModelRunResult, run_models
from heatmap_core.normalize.pricing import PriceSource
from heatmap_core.normalize.run import NormalizeResult, normalize_pending
from heatmap_core.providers.errors import AllProvidersExhaustedError, ProviderError

log = get_logger(__name__)


@dataclass
class SyncRunResult:
    vetted: int = 0
    rejected: int = 0
    synced: int = 0
    inserted: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    stopped_early: bool = False
    classified: int = 0
    skipped: bool = False


@dataclass
class DiscoveryResult:
    from_block: int = 0
    to_block: int = 0
    swaps: int = 0
    trades: int = 0
    unresolved: int = 0
    valued: int = 0
    traders: int = 0
    bots: int = 0
    promoted: int = 0
    error: str | None = None
    skipped: bool = False


@contextmanager
def stage_lock(engine: Engine, stage: str, chain_id: int) -> Iterator[bool]:
    """Hold the advisory lock for ``stage`` on ``chain_id``; yields False if another run has it.

    The lock belongs to the database session, so it is released if the process dies.
    """
    params = {"stage": stage, "chain_id": chain_id}
    with engine.connect() as conn:
        acquired = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:stage), :chain_id)"), params
            ).scalar()
        )
        conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:stage), :chain_id)"), params)
                conn.commit()
            else:
                log.info("stage.skipped_busy", stage=stage, chain_id=chain_id)


def seed_reference_data(engine: Engine, chain: Chain) -> dict[str, int]:
    with session_scope(engine) as session:
        return {
            "labels": load_seed_labels(session, chain),
            "tokens": load_seed_tokens(session, chain),
        }


def discover_traders(
    engine: Engine,
    source: DexSource,
    chain: Chain,
    settings: Settings,
    prices: PriceSource | None,
) -> DiscoveryResult:
    """Scan new DEX trades, value them, score traders and promote the best to the watchlist.

    A provider failure stops the scan where it is (the cursor keeps the
    progress); scoring and promotion still run on what is stored.
    """
    if not settings.discovery.enabled:
        return DiscoveryResult()
    with stage_lock(engine, "discovery", chain.chain_id) as acquired:
        if not acquired:
            return DiscoveryResult(skipped=True)
        result = DiscoveryResult()
        try:
            ingest: IngestResult = ingest_swaps(engine, source, chain, settings)
            result.from_block, result.to_block = ingest.from_block, ingest.to_block
            result.swaps, result.trades, result.unresolved = (
                ingest.swaps,
                ingest.trades,
                ingest.unresolved,
            )
        except ProviderError as exc:
            log.warning("discovery.scan_stopped", error=str(exc))
            result.error = str(exc)
        result.valued = value_trades(engine, chain, prices)
        stats = refresh_traders(engine, chain, settings)
        result.traders, result.bots = stats.traders, stats.bots
        result.promoted = len(promote_traders(engine, chain, settings))
    return result


def sync_tracked_wallets(
    engine: Engine,
    source: TransferSource,
    chain: Chain,
    *,
    limit: int | None = None,
    only_new: bool = False,
    tracking: TrackingConfig | None = None,
) -> SyncRunResult:
    """Sync active watchlist wallets (or only never-synced ones) against one chain head.

    With ``tracking``, automatically added wallets are vetted first and the
    ones that are not people are deactivated (see ``ingestion.vetting``);
    wallets still unvetted after a provider failure wait for a later run.
    Afterwards, counterparties of tracked wallets are classified as EOA or
    contract within the chain's ``classify_per_sync`` budget.
    """
    with stage_lock(engine, "sync", chain.chain_id) as acquired:
        if not acquired:
            return SyncRunResult(skipped=True)
        return _sync(engine, source, chain, limit, only_new, tracking)


def _sync(
    engine: Engine,
    source: TransferSource,
    chain: Chain,
    limit: int | None,
    only_new: bool,
    tracking: TrackingConfig | None,
) -> SyncRunResult:
    result = SyncRunResult()
    if tracking is not None:
        vetting = vet_new_wallets(engine, source, chain, tracking)
        result.vetted, result.rejected = vetting.checked, len(vetting.rejected)
    with session_scope(engine) as session:
        if only_new:
            wallets = unsynced_addresses(session, chain.chain_id)[:limit]
        else:
            wallets = active_addresses(session, chain.chain_id, limit)
        if tracking is not None:
            waiting = set(unvetted_addresses(session, chain.chain_id))
            wallets = [w for w in wallets if w not in waiting]
    if not wallets:
        return result
    head = source.latest_block(chain)
    try:
        classify_addresses(engine, source, chain, wallets)
    except ProviderError as exc:
        log.warning("sync.classify_failed", error=str(exc))
    for wallet in wallets:
        try:
            outcome = sync_wallet(engine, source, chain, wallet, head=head)
        except AllProvidersExhaustedError as exc:
            # Every key is out: stop instead of failing each remaining wallet.
            record_sync_error(engine, chain, wallet, str(exc))
            result.failed[wallet] = str(exc)
            result.stopped_early = True
            break
        except ProviderError as exc:
            record_sync_error(engine, chain, wallet, str(exc))
            result.failed[wallet] = str(exc)
            continue
        result.synced += 1
        result.inserted += outcome.inserted
    if not result.stopped_early:
        try:
            result.classified = classify_counterparties(
                engine, source, chain, chain.config.classify_per_sync
            )
        except ProviderError as exc:
            log.warning("sync.classify_counterparties_failed", error=str(exc))
    log.info(
        "sync.run_done",
        chain=chain.name,
        vetted=result.vetted,
        rejected=result.rejected,
        synced=result.synced,
        inserted=result.inserted,
        failed=len(result.failed),
        stopped_early=result.stopped_early,
        classified=result.classified,
    )
    return result


def normalize(
    engine: Engine, chain: Chain, settings: Settings, prices: PriceSource | None
) -> NormalizeResult:
    with stage_lock(engine, "normalize", chain.chain_id) as acquired:
        if not acquired:
            return NormalizeResult(skipped=True)
        return normalize_pending(engine, chain, settings, prices)


def refresh_graph(engine: Engine, chain: Chain, settings: Settings) -> dict[str, Any]:
    with stage_lock(engine, "graph", chain.chain_id) as acquired:
        if not acquired:
            return {"skipped": True}
        edges = rebuild_edges(engine, chain.chain_id)
        expansion: ExpansionResult = expand_neighbours(engine, chain, settings)
        busy = high_degree_addresses(
            engine, chain.chain_id, settings.expansion.hub_degree_threshold
        )
        communities = detect_communities(engine, chain.chain_id, exclude=busy)
    return {
        "edges": edges,
        "neighbours_added": len(expansion.added),
        "hubs_skipped": len(expansion.skipped_hubs),
        "budget_reached": expansion.capped,
        "communities": communities,
        "skipped": False,
    }


# Features and models share a lock so models never label a snapshot that is
# still being written.
BEHAVIOUR_LOCK = "behaviour"


def compute_behaviour(
    engine: Engine, chain: Chain, settings: Settings, snapshot_at: datetime | None = None
) -> FeatureRunResult:
    with stage_lock(engine, BEHAVIOUR_LOCK, chain.chain_id) as acquired:
        if not acquired:
            return FeatureRunResult(snapshot_at=datetime.now(UTC), skipped=True)
        return compute_features(engine, chain, settings, snapshot_at=snapshot_at)


def label_wallets(
    engine: Engine, chain: Chain, settings: Settings, snapshot_at: datetime | None = None
) -> ModelRunResult:
    with stage_lock(engine, BEHAVIOUR_LOCK, chain.chain_id) as acquired:
        if not acquired:
            return ModelRunResult(snapshot_at=None, skipped=True)
        return run_models(engine, chain, settings, snapshot_at=snapshot_at)
