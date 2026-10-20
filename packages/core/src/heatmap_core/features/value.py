"""USD flows."""

from __future__ import annotations

import polars as pl

from heatmap_core.features.context import FeatureContext

FUNGIBLE = ("external", "internal", "erc20")


def compute(ctx: FeatureContext) -> pl.DataFrame:
    usd = pl.col("amount_usd")
    is_in = pl.col("direction") == "in"
    return (
        ctx.sides.group_by("wallet")
        .agg(
            usd.sum().alias("volume_usd"),
            usd.filter(is_in).sum().alias("inflow_usd"),
            usd.filter(~is_in).sum().alias("outflow_usd"),
            usd.median().alias("median_transfer_usd"),
            usd.max().alias("max_transfer_usd"),
            usd.filter(pl.col("category").is_in(FUNGIBLE))
            .is_not_null()
            .mean()
            .alias("priced_share"),
        )
        .with_columns((pl.col("inflow_usd") - pl.col("outflow_usd")).alias("netflow_usd"))
    )
