"""When a wallet is active (UTC). The hour/weekday histograms drive the heatmaps."""

from __future__ import annotations

import polars as pl

from heatmap_core.features.asset_mix import entropy
from heatmap_core.features.context import FeatureContext


def _histogram(df: pl.DataFrame, column: str, size: int, name: str) -> pl.DataFrame:
    counts = df.group_by("wallet", column).len()
    totals = counts.group_by("wallet").agg(pl.col("len").sum().alias("_total"))
    grid = (
        df.select("wallet")
        .unique()
        .join(
            pl.DataFrame({column: list(range(size))}, schema={column: counts.schema[column]}),
            how="cross",
        )
    )
    return (
        grid.join(counts, on=["wallet", column], how="left")
        .join(totals, on="wallet")
        .with_columns((pl.col("len").fill_null(0) / pl.col("_total")).alias("_share"))
        .sort("wallet", column)
        .group_by("wallet", maintain_order=True)
        .agg(pl.col("_share").alias(name))
    )


def compute(ctx: FeatureContext) -> pl.DataFrame:
    df = ctx.sides.with_columns(
        pl.col("block_time").dt.hour().alias("hour"),
        (pl.col("block_time").dt.weekday() - 1).alias("weekday"),  # 0 = Monday
    )
    scalars = df.group_by("wallet").agg(
        (pl.col("hour") < 6).mean().alias("night_share"),
        (pl.col("weekday") >= 5).mean().alias("weekend_share"),
        entropy("hour").alias("hour_entropy"),
    )
    return scalars.join(_histogram(df, "hour", 24, "hour_hist"), on="wallet").join(
        _histogram(df, "weekday", 7, "weekday_hist"), on="wallet"
    )
