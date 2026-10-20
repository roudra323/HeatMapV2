"""What a wallet holds and moves, by token category."""

from __future__ import annotations

import polars as pl

from heatmap_core.features.context import FeatureContext
from heatmap_core.primitives import TokenCategory


def entropy(column: str) -> pl.Expr:
    """Shannon entropy (nats) of the value distribution of ``column`` within a group."""
    p = pl.col(column).value_counts(normalize=True).struct.field("proportion")
    return -(p * p.log()).sum()


def compute(ctx: FeatureContext) -> pl.DataFrame:
    category = pl.col("token_category")
    return ctx.sides.group_by("wallet").agg(
        *[(category == c.value).mean().alias(f"share_{c.value}") for c in TokenCategory],
        pl.col("token_address").n_unique().alias("distinct_tokens"),
        entropy("token_address").alias("token_entropy"),
        pl.col("token_address")
        .filter(pl.col("category").is_in(["erc721", "erc1155"]))
        .n_unique()
        .alias("nft_collections"),
    )
