"""Feature groups, in the order they are joined.

Add a group by writing a module with ``compute(ctx) -> DataFrame`` keyed by
``wallet`` and listing it here; bump ``FEATURE_VERSION`` when outputs change.
"""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from heatmap_core.features import activity, asset_mix, neighbourhood, protocol, timing, value
from heatmap_core.features.context import FeatureContext

FEATURE_VERSION = "f1"

FeatureGroup = Callable[[FeatureContext], pl.DataFrame]

GROUPS: dict[str, FeatureGroup] = {
    "activity": activity.compute,
    "value": value.compute,
    "asset_mix": asset_mix.compute,
    "timing": timing.compute,
    "protocol": protocol.compute,
    "neighbourhood": neighbourhood.compute,
}


def compute_all(ctx: FeatureContext) -> pl.DataFrame:
    frames = [group(ctx) for group in GROUPS.values()]
    result = frames[0]
    for frame in frames[1:]:
        result = result.join(frame, on="wallet", how="left")
    return result.join(neighbourhood.neighbour_means(ctx.sides, result), on="wallet", how="left")
