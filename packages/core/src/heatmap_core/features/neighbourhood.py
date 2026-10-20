"""A wallet's position among its counterparties and the other tracked wallets."""

from __future__ import annotations

import polars as pl

from heatmap_core.features.asset_mix import entropy
from heatmap_core.features.context import FeatureContext

# Counterparties shared by more tracked wallets than this are too generic to link them.
MAX_SHARED = 200


def _shared_counterparty_pairs(sides: pl.DataFrame) -> pl.DataFrame:
    links = sides.filter(~pl.col("cp_is_hub")).select("wallet", "counterparty").unique()
    popular = links.group_by("counterparty").len().filter(pl.col("len") <= MAX_SHARED)
    links = links.join(popular.select("counterparty"), on="counterparty")
    return (
        links.join(links, on="counterparty", suffix="_other")
        .filter(pl.col("wallet") != pl.col("wallet_other"))
        .group_by("wallet", "wallet_other")
        .len("shared")
    )


def _similarity(sides: pl.DataFrame) -> pl.DataFrame:
    degree = (
        sides.filter(~pl.col("cp_is_hub"))
        .group_by("wallet")
        .agg(pl.col("counterparty").n_unique().alias("deg"))
    )
    pairs = (
        _shared_counterparty_pairs(sides)
        .join(degree, on="wallet")
        .join(degree.rename({"wallet": "wallet_other", "deg": "deg_other"}), on="wallet_other")
        .with_columns(
            (pl.col("shared") / (pl.col("deg") + pl.col("deg_other") - pl.col("shared"))).alias(
                "jaccard"
            )
        )
        .sort(["wallet", "jaccard", "wallet_other"], descending=[False, True, False])
    )
    return pairs.group_by("wallet", maintain_order=True).agg(
        pl.col("jaccard").first().alias("max_counterparty_jaccard"),
        pl.col("wallet_other").first().alias("most_similar_wallet"),
        pl.len().alias("wallets_sharing_counterparties"),
    )


def _co_timing(sides: pl.DataFrame, seconds: int) -> pl.DataFrame:
    events = (
        sides.filter(~pl.col("cp_is_hub"))
        .with_columns((pl.col("block_time").dt.epoch("s") // seconds).alias("bucket"))
        .select("wallet", "counterparty", "bucket")
        .unique()
    )
    return (
        events.join(events, on=["counterparty", "bucket"], suffix="_other")
        .filter(pl.col("wallet") != pl.col("wallet_other"))
        .group_by("wallet")
        .agg(pl.col("wallet_other").n_unique().alias("co_timed_wallets"))
    )


def compute(ctx: FeatureContext) -> pl.DataFrame:
    s = ctx.sides
    per_cp = s.group_by("wallet", "counterparty").len()
    base = s.group_by("wallet").agg(
        pl.col("counterparty").n_unique().alias("degree"),
        pl.col("counterparty").filter(pl.col("direction") == "in").n_unique().alias("in_degree"),
        pl.col("counterparty").filter(pl.col("direction") == "out").n_unique().alias("out_degree"),
        pl.col("cp_is_hub").mean().alias("hub_share"),
        pl.col("counterparty").filter(pl.col("cp_tracked")).n_unique().alias("tracked_neighbours"),
        entropy("counterparty").alias("counterparty_entropy"),
    )
    top = per_cp.group_by("wallet").agg(
        (pl.col("len").max() / pl.col("len").sum()).alias("top_counterparty_share")
    )

    wallets = ctx.wallets
    # Exchanges fund everyone, so only wallets funded by a non-hub address form a cluster.
    private = pl.col("funded_by").is_not_null() & ~pl.col("funder_is_hub").fill_null(False)
    funders = wallets.filter(private).group_by("funded_by").len("funder_cluster_size")
    identity = wallets.join(funders, on="funded_by", how="left").select(
        "wallet",
        "funded_by",
        "community_id",
        pl.col("funder_cluster_size").fill_null(0),
    )

    return (
        base.join(top, on="wallet", how="left")
        .join(identity, on="wallet", how="left")
        .join(_similarity(s), on="wallet", how="left")
        .join(_co_timing(s, ctx.co_timing_seconds), on="wallet", how="left")
        .with_columns(
            pl.col("co_timed_wallets").fill_null(0),
            pl.col("wallets_sharing_counterparties").fill_null(0),
            pl.col("max_counterparty_jaccard").fill_null(0.0),
        )
    )


NEIGHBOUR_MEAN_FEATURES = ("transfer_count", "volume_usd", "share_stablecoin", "share_cex")


def neighbour_means(sides: pl.DataFrame, features: pl.DataFrame) -> pl.DataFrame:
    """Average of selected features over each wallet's tracked counterparties."""
    available = [c for c in NEIGHBOUR_MEAN_FEATURES if c in features.columns]
    links = (
        sides.filter(pl.col("cp_tracked"))
        .select("wallet", pl.col("counterparty").alias("neighbour"))
        .unique()
    )
    neighbour_values = features.select(pl.col("wallet").alias("neighbour"), *available)
    return (
        links.join(neighbour_values, on="neighbour")
        .group_by("wallet")
        .agg(*[pl.col(c).mean().alias(f"neighbour_mean_{c}") for c in available])
    )
