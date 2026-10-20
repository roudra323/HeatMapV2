"""Stage functions shared by Dagster assets, the CLI and tests.

Each stage reads its inputs from the database and writes its outputs back,
so stages can run independently and on their own schedules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Engine

from heatmap_core.config import Chain, Settings
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import load_seed_labels, load_seed_tokens
from heatmap_core.features.run import FeatureRunResult, compute_features
from heatmap_core.graph.communities import detect_communities
from heatmap_core.graph.edges import rebuild_edges
from heatmap_core.graph.expansion import ExpansionResult, expand_neighbours
from heatmap_core.ingestion.sync import (
    TransferSource,
    classify_addresses,
    record_sync_error,
    sync_wallet,
)
from heatmap_core.ingestion.watchlist import active_addresses
from heatmap_core.logging import get_logger
from heatmap_core.models.run import ModelRunResult, run_models
from heatmap_core.normalize.pricing import PriceSource
from heatmap_core.normalize.run import NormalizeResult, normalize_pending
from heatmap_core.providers.errors import AllProvidersExhaustedError, ProviderError

log = get_logger(__name__)


@dataclass
class SyncRunResult:
    synced: int = 0
    inserted: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    stopped_early: bool = False


def seed_reference_data(engine: Engine, chain: Chain) -> dict[str, int]:
    with session_scope(engine) as session:
        return {
            "labels": load_seed_labels(session, chain),
            "tokens": load_seed_tokens(session, chain),
        }


def sync_tracked_wallets(
    engine: Engine,
    source: TransferSource,
    chain: Chain,
    *,
    limit: int | None = None,
) -> SyncRunResult:
    """Sync every active watchlist wallet against one shared chain head."""
    result = SyncRunResult()
    with session_scope(engine) as session:
        wallets = active_addresses(session, chain.chain_id, limit)
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
    log.info(
        "sync.run_done",
        chain=chain.name,
        synced=result.synced,
        inserted=result.inserted,
        failed=len(result.failed),
        stopped_early=result.stopped_early,
    )
    return result


def normalize(
    engine: Engine, chain: Chain, settings: Settings, prices: PriceSource | None
) -> NormalizeResult:
    return normalize_pending(engine, chain, settings, prices)


def refresh_graph(engine: Engine, chain: Chain, settings: Settings) -> dict[str, Any]:
    edges = rebuild_edges(engine, chain.chain_id)
    expansion: ExpansionResult = expand_neighbours(engine, chain, settings)
    communities = detect_communities(engine, chain.chain_id)
    return {
        "edges": edges,
        "neighbours_added": len(expansion.added),
        "hubs_skipped": len(expansion.skipped_hubs),
        "budget_reached": expansion.capped,
        "communities": communities,
    }


def compute_behaviour(
    engine: Engine, chain: Chain, settings: Settings, snapshot_at: datetime | None = None
) -> FeatureRunResult:
    return compute_features(engine, chain, settings, snapshot_at=snapshot_at)


def label_wallets(
    engine: Engine, chain: Chain, settings: Settings, snapshot_at: datetime | None = None
) -> ModelRunResult:
    return run_models(engine, chain, settings, snapshot_at=snapshot_at)
