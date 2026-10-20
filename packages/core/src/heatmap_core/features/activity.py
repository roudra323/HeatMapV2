"""How much and how regularly a wallet transacts."""

from __future__ import annotations

import polars as pl

from heatmap_core.features.context import FeatureContext


def compute(ctx: FeatureContext) -> pl.DataFrame:
    s = ctx.sides
    snapshot = pl.lit(ctx.snapshot_at).cast(pl.Datetime(time_zone="UTC"))
    base = s.group_by("wallet").agg(
        pl.len().alias("transfer_count"),
        pl.col("tx_hash").n_unique().alias("tx_count"),
        pl.col("block_time").dt.date().n_unique().alias("active_days"),
        (
            (pl.col("block_time").max() - pl.col("block_time").min()).dt.total_seconds() / 86400
        ).alias("lifespan_days"),
        ((snapshot - pl.col("block_time").max()).dt.total_seconds() / 86400).alias(
            "days_since_last"
        ),
        (pl.col("direction") == "out").mean().alias("out_share"),
    )
    base = base.with_columns(
        (pl.col("tx_count") / pl.col("active_days")).alias("tx_per_active_day")
    )

    # Gaps between consecutive distinct transactions.
    txs = (
        s.group_by("wallet", "tx_hash").agg(pl.col("block_time").min()).sort("wallet", "block_time")
    )
    gaps = (
        txs.with_columns(
            (pl.col("block_time").diff().over("wallet").dt.total_seconds() / 3600).alias("gap_h")
        )
        .drop_nulls("gap_h")
        .group_by("wallet")
        .agg(
            pl.col("gap_h").median().alias("median_gap_hours"),
            pl.col("gap_h").mean().alias("_mean"),
            pl.col("gap_h").std().alias("_std"),
            # share of gaps within 10% of the median gap: high values look scripted
            ((pl.col("gap_h") - pl.col("gap_h").median()).abs() <= 0.1 * pl.col("gap_h").median())
            .mean()
            .alias("gap_regularity"),
        )
        .with_columns(
            # Goh-Barabasi burstiness in [-1, 1]: -1 periodic, 0 random, 1 bursty
            pl.when(pl.col("_std") + pl.col("_mean") > 0)
            .then((pl.col("_std") - pl.col("_mean")) / (pl.col("_std") + pl.col("_mean")))
            .otherwise(None)
            .alias("burstiness")
        )
        .drop("_mean", "_std")
    )
    return base.join(gaps, on="wallet", how="left")
