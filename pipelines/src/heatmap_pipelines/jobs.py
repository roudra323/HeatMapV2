"""Jobs for each cadence and the schedules/sensors that trigger them."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator

import dagster as dg

from heatmap_core.config import ChainRegistry, Settings
from heatmap_core.db.session import get_engine, session_scope
from heatmap_core.ingestion.watchlist import unsynced_addresses
from heatmap_pipelines.assets import (
    SCOPE_NEW,
    SCOPE_TAG,
    dex_traders,
    normalized_transfers,
    raw_transfers,
    reference_data,
    wallet_features,
    wallet_graph,
    wallet_labels,
)

discovery_job = dg.define_asset_job(
    "discovery_job",
    selection=dg.AssetSelection.assets(dex_traders),
    description="Scan DEX trades, score traders, promote the best to the watchlist",
)
sync_job = dg.define_asset_job(
    "sync_job",
    selection=dg.AssetSelection.assets(reference_data, raw_transfers, normalized_transfers),
    description="Pull new transfers for tracked wallets and normalise them",
)
expansion_job = dg.define_asset_job(
    "expansion_job",
    selection=dg.AssetSelection.assets(wallet_graph),
    description="Rebuild edges, discover neighbours, detect communities",
)
features_job = dg.define_asset_job(
    "features_job",
    selection=dg.AssetSelection.assets(wallet_features, wallet_labels),
    description="Behaviour snapshot, then tags, clusters, anomalies and drift on it",
)
models_job = dg.define_asset_job(
    "models_job",
    selection=dg.AssetSelection.assets(wallet_labels),
    description="Re-label the latest snapshot (not scheduled; features_job runs models)",
)
full_refresh_job = dg.define_asset_job(
    "full_refresh_job",
    selection=dg.AssetSelection.all(),
    description="Every stage in order",
)

JOBS = [discovery_job, sync_job, expansion_job, features_job, models_job, full_refresh_job]


def _per_chain(settings: Settings) -> list[str]:
    return [c.name for c in ChainRegistry(settings).all()]


def build_schedules(settings: Settings) -> list[dg.ScheduleDefinition]:
    """One schedule per cadence; crons come from ``schedules.*`` in config."""
    cfg = settings.schedules
    status = dg.DefaultScheduleStatus.RUNNING if cfg.enabled else dg.DefaultScheduleStatus.STOPPED
    chain_names = _per_chain(settings)
    schedules = []
    for job, cron in (
        (discovery_job, cfg.discovery_cron),
        (sync_job, cfg.sync_cron),
        (expansion_job, cfg.expansion_cron),
        (features_job, cfg.features_cron),
    ):

        def evaluate(
            context: dg.ScheduleEvaluationContext, job_name: str = job.name
        ) -> Iterator[dg.RunRequest]:
            stamp = context.scheduled_execution_time.isoformat()
            for chain in chain_names:
                yield dg.RunRequest(run_key=f"{job_name}:{chain}:{stamp}", partition_key=chain)

        schedules.append(
            dg.ScheduleDefinition(
                name=f"{job.name}_schedule",
                cron_schedule=cron,
                job=job,
                execution_fn=evaluate,
                execution_timezone=cfg.timezone,
                default_status=status,
            )
        )
    return schedules


# A wallet still unsynced after this long (its run was skipped because another
# sync held the lock) is requested again.
RETRY_SECONDS = 600


def build_sensors(settings: Settings) -> list[dg.SensorDefinition]:
    chain_list = ChainRegistry(settings).all()

    @dg.sensor(
        job=sync_job, minimum_interval_seconds=60, default_status=dg.DefaultSensorStatus.RUNNING
    )
    def new_watchlist_wallets(context: dg.SensorEvaluationContext) -> Iterator[dg.RunRequest]:
        """Sync wallets added to the watchlist (e.g. via the API) without waiting for the cron.

        The run syncs only never-synced wallets, not the whole watchlist.
        """
        window = int(time.time()) // RETRY_SECONDS
        with session_scope(get_engine()) as session:
            pending = {c.name: unsynced_addresses(session, c.chain_id) for c in chain_list}
        for chain_name, addresses in pending.items():
            if addresses:
                digest = hashlib.sha256(",".join(addresses).encode()).hexdigest()[:16]
                yield dg.RunRequest(
                    run_key=f"{chain_name}:{digest}:{window}",
                    partition_key=chain_name,
                    tags={SCOPE_TAG: SCOPE_NEW},
                )

    return [new_watchlist_wallets]
