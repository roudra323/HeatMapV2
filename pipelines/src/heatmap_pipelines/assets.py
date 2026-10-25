"""Pipeline stages as Dagster assets, partitioned by chain."""

import dagster as dg

from heatmap_core import pipeline
from heatmap_core.config import ChainRegistry, get_settings
from heatmap_pipelines.resources import HeatmapResource

chains = dg.StaticPartitionsDefinition(
    [c.name for c in ChainRegistry(get_settings()).all()] or ["ethereum"]
)

GROUP = "heatmap"
# Run tag: "new" syncs only never-synced wallets (set by the watchlist sensor).
SCOPE_TAG = "heatmap/sync_scope"
SCOPE_NEW = "new"


@dg.asset(partitions_def=chains, group_name=GROUP, description="Seeded hub labels and tokens")
def reference_data(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    counts = pipeline.seed_reference_data(heatmap.engine, heatmap.chain(context.partition_key))
    return dg.MaterializeResult(metadata=counts)


@dg.asset(
    partitions_def=chains,
    group_name=GROUP,
    deps=[reference_data],
    description="New DEX swaps, trader scores, and traders promoted to the watchlist",
)
def dex_traders(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    with heatmap.router() as router:
        result = pipeline.discover_traders(
            heatmap.engine, router, chain, heatmap.settings, heatmap.prices()
        )
    if result.error:
        context.log.warning(f"trade scan stopped early: {result.error}")
    return dg.MaterializeResult(
        metadata={k: v for k, v in result.__dict__.items() if k != "error" and v is not None}
    )


@dg.asset(
    partitions_def=chains,
    group_name=GROUP,
    deps=[reference_data],
    description="New transfers for every active watchlist wallet",
)
def raw_transfers(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    only_new = context.run.tags.get(SCOPE_TAG) == SCOPE_NEW
    with heatmap.router() as router:
        result = pipeline.sync_tracked_wallets(
            heatmap.engine, router, chain, only_new=only_new, tracking=heatmap.settings.tracking
        )
    if result.failed:
        context.log.warning(f"{len(result.failed)} wallets failed to sync")
    return dg.MaterializeResult(
        metadata={
            "wallets_vetted": result.vetted,
            "wallets_rejected": result.rejected,
            "wallets_synced": result.synced,
            "transfers_inserted": result.inserted,
            "wallets_failed": len(result.failed),
            "stopped_early": result.stopped_early,
            "counterparties_classified": result.classified,
            "only_new": only_new,
            "skipped_busy": result.skipped,
        }
    )


@dg.asset(
    partitions_def=chains,
    group_name=GROUP,
    deps=[raw_transfers],
    description="Amounts, USD values, spam flags and funding sources",
)
def normalized_transfers(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    result = pipeline.normalize(heatmap.engine, chain, heatmap.settings, heatmap.prices())
    return dg.MaterializeResult(metadata=dict(result.__dict__))


@dg.asset(
    partitions_def=chains,
    group_name=GROUP,
    deps=[normalized_transfers],
    description="Edges, neighbour expansion and communities",
)
def wallet_graph(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    return dg.MaterializeResult(
        metadata=pipeline.refresh_graph(heatmap.engine, chain, heatmap.settings)
    )


@dg.asset(
    partitions_def=chains,
    group_name=GROUP,
    deps=[wallet_graph],
    description="Behaviour feature snapshot per wallet and window",
)
def wallet_features(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    result = pipeline.compute_behaviour(heatmap.engine, chain, heatmap.settings)
    return dg.MaterializeResult(
        metadata={
            "snapshot_at": result.snapshot_at.isoformat(),
            "rows": result.rows,
            **{f"wallets_{w}": n for w, n in result.wallets_by_window.items()},
            "skipped_busy": result.skipped,
        }
    )


@dg.asset(
    partitions_def=chains,
    group_name=GROUP,
    deps=[wallet_features],
    description="Tags, clusters, anomaly scores and drift for the latest snapshot",
)
def wallet_labels(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    result = pipeline.label_wallets(heatmap.engine, chain, heatmap.settings)
    return dg.MaterializeResult(
        metadata={
            "snapshot_at": result.snapshot_at.isoformat() if result.snapshot_at else "none",
            "tags": result.tags,
            "clusters": result.clusters,
            "anomalies": result.anomalies,
            "drifted": result.drifted,
            "skipped_busy": result.skipped,
        }
    )


ALL_ASSETS = [
    reference_data,
    dex_traders,
    raw_transfers,
    normalized_transfers,
    wallet_graph,
    wallet_features,
    wallet_labels,
]
