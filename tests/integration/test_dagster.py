from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import dagster as dg
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.db.models import WalletFeatureSnapshot, WatchlistEntry
from heatmap_core.db.session import session_scope
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_pipelines import jobs
from heatmap_pipelines.assets import ALL_ASSETS, SCOPE_NEW, SCOPE_TAG
from heatmap_pipelines.jobs import build_schedules, build_sensors
from heatmap_pipelines.resources import HeatmapResource
from tests.support import FakeSource, addr, raw

SEED = addr(1)


def make_resource(engine: Engine, source: FakeSource) -> HeatmapResource:
    class TestResource(HeatmapResource):
        @property
        def engine(self) -> Engine:  # type: ignore[override]
            return engine

        @property
        def settings(self) -> Settings:  # type: ignore[override]
            return Settings(
                expansion={"min_interactions": 1, "window_days": 100_000},
                features={"min_transfers": 1},
                pricing={"enabled": False},
                discovery={"enabled": False},  # covered by test_discovery
            )

        @contextmanager
        def router(self) -> Iterator[Any]:
            yield source

    return TestResource()


def test_materialize_all_assets(engine: Engine, session: Session) -> None:
    with session_scope(engine) as s:
        add_seed(s, 1, SEED)
    source = FakeSource([raw(1, addr(2), SEED), raw(2, SEED, addr(3)), raw(3, SEED, addr(3))])

    result = dg.materialize(
        ALL_ASSETS, partition_key="ethereum", resources={"heatmap": make_resource(engine, source)}
    )

    assert result.success
    metadata = {
        e.asset_key.to_user_string(): e.step_materialization_data.materialization.metadata
        for e in result.get_asset_materialization_events()
    }
    assert metadata["raw_transfers"]["wallets_synced"].value == 1
    assert metadata["wallet_graph"]["neighbours_added"].value == 2
    assert session.scalars(select(WatchlistEntry)).all()
    assert session.scalars(select(WalletFeatureSnapshot)).all()


def test_schedules_follow_config() -> None:
    settings = Settings(
        chains={"ethereum": {"chain_id": 1}},
        schedules={"sync_cron": "*/10 * * * *", "enabled": False},
    )
    schedules = {s.name: s for s in build_schedules(settings)}
    sync = schedules["sync_job_schedule"]
    assert sync.cron_schedule == "*/10 * * * *"
    assert sync.default_status == dg.DefaultScheduleStatus.STOPPED

    repo = dg.Definitions(
        assets=ALL_ASSETS, schedules=[sync], resources={"heatmap": HeatmapResource()}
    ).get_repository_def()
    context = dg.build_schedule_context(
        scheduled_execution_time=datetime(2026, 1, 1, tzinfo=UTC), repository_def=repo
    )
    requests = list(sync.evaluate_tick(context).run_requests or [])
    assert [r.partition_key for r in requests] == ["ethereum"]


def test_models_run_inside_the_features_job() -> None:
    schedules = build_schedules(Settings(chains={"ethereum": {"chain_id": 1}}))
    assert {s.name for s in schedules} == {
        "discovery_job_schedule",
        "sync_job_schedule",
        "expansion_job_schedule",
        "features_job_schedule",
    }
    repo = dg.Definitions(
        assets=ALL_ASSETS, jobs=jobs.JOBS, resources={"heatmap": HeatmapResource()}
    ).get_repository_def()
    selected = repo.get_job("features_job").asset_layer.executable_asset_keys
    assert {k.to_user_string() for k in selected} == {"wallet_features", "wallet_labels"}


def test_sensor_requests_sync_for_unsynced_wallets(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "get_engine", lambda: engine)
    with session_scope(engine) as s:
        add_seed(s, 1, SEED)
    (sensor,) = build_sensors(Settings(chains={"ethereum": {"chain_id": 1}}))
    repo = dg.Definitions(
        assets=ALL_ASSETS, sensors=[sensor], resources={"heatmap": HeatmapResource()}
    ).get_repository_def()
    context = dg.build_sensor_context(repository_def=repo)
    requests = list(sensor.evaluate_tick(context).run_requests or [])
    assert [r.partition_key for r in requests] == ["ethereum"]
    assert requests[0].tags[SCOPE_TAG] == SCOPE_NEW  # only the new wallets are synced
