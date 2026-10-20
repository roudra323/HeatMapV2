"""Dagster entry point: ``dagster dev -m heatmap_pipelines.definitions``."""

from __future__ import annotations

import dagster as dg

from heatmap_core.config import get_settings
from heatmap_core.logging import configure_logging
from heatmap_pipelines.assets import ALL_ASSETS
from heatmap_pipelines.jobs import JOBS, build_schedules, build_sensors
from heatmap_pipelines.resources import HeatmapResource

_settings = get_settings()
configure_logging(_settings.log_level, _settings.log_json)

defs = dg.Definitions(
    assets=ALL_ASSETS,
    jobs=JOBS,
    schedules=build_schedules(_settings),
    sensors=build_sensors(_settings),
    resources={"heatmap": HeatmapResource()},
)
