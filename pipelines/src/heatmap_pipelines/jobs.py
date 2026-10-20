"""Jobs for each cadence and the schedules/sensors that trigger them."""

from __future__ import annotations

from collections.abc import Iterator

import dagster as dg
from sqlalchemy import text

from heatmap_core.config import ChainRegistry, Settings
from heatmap_core.db.session import get_engine
from heatmap_pipelines.assets import (
    normalized_transfers,
    raw_transfers,
    reference_data,
    wallet_features,
    wallet_graph,
    wallet_labels,
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
    selection=dg.AssetSelection.assets(wallet_features),
)
models_job = dg.define_asset_job(
    "models_job",
    selection=dg.AssetSelection.assets(wallet_labels),
)
full_refresh_job = dg.define_asset_job(
    "full_refresh_job",
    selection=dg.AssetSelection.all(),
    description="Every stage in order",
)

JOBS = [sync_job, expansion_job, features_job, models_job, full_refresh_job]


def _per_chain(settings: Settings) -> list[str]:
    return [c.name for c in ChainRegistry(settings).all()]


def build_schedules(settings: Settings) -> list[dg.ScheduleDefinition]:
    """One schedule per cadence; crons come from ``schedules.*`` in config."""
    cfg = settings.schedules
    status = dg.DefaultScheduleStatus.RUNNING if cfg.enabled else dg.DefaultScheduleStatus.STOPPED
    chain_names = _per_chain(settings)
    schedules = []
    for job, cron in (
        (sync_job, cfg.sync_cron),
        (expansion_job, cfg.expansion_cron),
        (features_job, cfg.features_cron),
        (models_job, cfg.models_cron),
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


NEW_SEEDS_SQL = text(
    """
    SELECT w.address FROM watchlist w
    LEFT JOIN sync_cursors c ON c.chain_id = w.chain_id AND c.address = w.address
    WHERE w.chain_id = :chain_id AND w.active AND c.address IS NULL
    ORDER BY w.address
    """
)


def build_sensors(settings: Settings) -> list[dg.SensorDefinition]:
    chain_list = ChainRegistry(settings).all()

    @dg.sensor(
        job=sync_job, minimum_interval_seconds=60, default_status=dg.DefaultSensorStatus.RUNNING
    )
    def new_watchlist_wallets(context: dg.SensorEvaluationContext) -> Iterator[dg.RunRequest]:
        """Sync wallets added to the watchlist (e.g. via the API) without waiting for the cron."""
        engine = get_engine()
        with engine.connect() as conn:
            for chain in chain_list:
                pending = list(conn.execute(NEW_SEEDS_SQL, {"chain_id": chain.chain_id}).scalars())
                if pending:
                    key = f"{chain.name}:{','.join(pending)}"
                    yield dg.RunRequest(run_key=key[:500], partition_key=chain.name)

    return [new_watchlist_wallets]
