"""Which kinds of services a wallet uses, from labelled counterparties."""

from __future__ import annotations

import polars as pl

from heatmap_core.features.context import FeatureContext
from heatmap_core.primitives import EntityCategory

TRACKED_ENTITIES = (
    EntityCategory.CEX,
    EntityCategory.DEX_ROUTER,
    EntityCategory.BRIDGE,
    EntityCategory.NFT_MARKETPLACE,
    EntityCategory.LENDING,
    EntityCategory.MIXER,
)


def compute(ctx: FeatureContext) -> pl.DataFrame:
    entity = pl.col("cp_entity")
    calls = (pl.col("direction") == "out") & pl.col("cp_is_contract")
    return ctx.sides.group_by("wallet").agg(
        *[
            # unlabelled counterparties are null and must count as "not this entity"
            (entity == e.value).fill_null(False).mean().alias(f"share_{e.value}")
            for e in TRACKED_ENTITIES
        ],
        calls.sum().alias("contract_interactions"),
        pl.col("counterparty").filter(calls).n_unique().alias("distinct_contracts"),
    )
