"""Pipeline stages as Dagster assets, partitioned by chain."""

import dagster as dg

from heatmap_core import pipeline
from heatmap_core.config import ChainRegistry, get_settings
from heatmap_pipelines.resources import HeatmapResource

chains = dg.StaticPartitionsDefinition(
    [c.name for c in ChainRegistry(get_settings()).all()] or ["ethereum"]
)

GROUP = "heatmap"


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
    description="New transfers for every active watchlist wallet",
)
def raw_transfers(
    context: dg.AssetExecutionContext, heatmap: HeatmapResource
) -> dg.MaterializeResult[None]:
    chain = heatmap.chain(context.partition_key)
    with heatmap.router() as router:
        result = pipeline.sync_tracked_wallets(heatmap.engine, router, chain)
    if result.failed:
        context.log.warning(f"{len(result.failed)} wallets failed to sync")
    return dg.MaterializeResult(
        metadata={
            "wallets_synced": result.synced,
            "transfers_inserted": result.inserted,
            "wallets_failed": len(result.failed),
            "stopped_early": result.stopped_early,
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
        }
    )


ALL_ASSETS = [
    reference_data,
    raw_transfers,
    normalized_transfers,
    wallet_graph,
    wallet_features,
    wallet_labels,
]
