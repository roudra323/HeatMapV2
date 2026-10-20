from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from heatmap_api.deps import ChainDep, SessionDep
from heatmap_api.schemas import ClusterOut, ClusterPointOut, HeatmapOut
from heatmap_core.exports.heatmaps import segment_heatmap
from heatmap_core.exports.read_models import cluster_points, cluster_summaries, tag_counts

router = APIRouter(prefix="/v1", tags=["analytics"])


@router.get("/clusters", response_model=list[ClusterOut])
def clusters(session: SessionDep, chain: ChainDep) -> list[ClusterOut]:
    return [ClusterOut(**c.__dict__) for c in cluster_summaries(session, chain.chain_id)]


@router.get("/clusters/points", response_model=list[ClusterPointOut])
def points(
    session: SessionDep,
    chain: ChainDep,
    limit: Annotated[int, Query(ge=1, le=20_000)] = 5_000,
) -> list[ClusterPointOut]:
    return [ClusterPointOut(**p.__dict__) for p in cluster_points(session, chain.chain_id, limit)]


@router.get("/tags", response_model=dict[str, int])
def tags(session: SessionDep, chain: ChainDep) -> dict[str, int]:
    return tag_counts(session, chain.chain_id)


@router.get("/heatmaps/segments", response_model=HeatmapOut)
def segments(
    session: SessionDep,
    chain: ChainDep,
    by: Literal["cluster", "tag"] = "cluster",
    window: Annotated[str, Query(pattern=r"^(\d+d|all)$")] = "all",
) -> HeatmapOut:
    return HeatmapOut(**segment_heatmap(session, chain.chain_id, by=by, window=window).__dict__)
