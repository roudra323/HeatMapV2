from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from heatmap_api.deps import AddressDep, ChainDep, LimitDep, OffsetDep, SessionDep
from heatmap_api.routers.watchlist import to_out
from heatmap_api.schemas import (
    EdgeOut,
    EntityOut,
    FeatureSnapshotOut,
    HeatmapOut,
    LabelOut,
    NetworkOut,
    NodeOut,
    Page,
    SimilarWalletOut,
    TimelineBucketOut,
    TradeOut,
    TransferOut,
    WalletProfileOut,
)
from heatmap_core.exports.dex import wallet_trades
from heatmap_core.exports.heatmaps import wallet_activity_heatmap
from heatmap_core.exports.read_models import (
    similar_wallets,
    snapshot_history,
    wallet_profile,
    wallet_timeline,
    wallet_transfers,
)
from heatmap_core.graph.ego import ego_network
from heatmap_core.primitives import LabelKind

router = APIRouter(prefix="/v1/wallets", tags=["wallets"])

Window = Annotated[str, Query(pattern=r"^(\d+d|all)$")]


@router.get("/{address}", response_model=WalletProfileOut)
def get_wallet(
    address: AddressDep, session: SessionDep, chain: ChainDep, window: Window = "all"
) -> WalletProfileOut:
    profile = wallet_profile(session, chain.chain_id, address, window)
    if profile is None:
        raise HTTPException(status_code=404, detail="wallet not seen yet; add it to the watchlist")

    def first(kind: LabelKind) -> LabelOut | None:
        match = next((label for label in profile.labels if label.kind == kind), None)
        return LabelOut.model_validate(match) if match else None

    wallet = profile.wallet
    return WalletProfileOut(
        address=address,
        kind=wallet.kind if wallet else None,
        first_seen_at=wallet.first_seen_at if wallet else None,
        last_seen_at=wallet.last_seen_at if wallet else None,
        funded_by=wallet.funded_by if wallet else None,
        entity=EntityOut(
            name=profile.entity.name,
            category=profile.entity.category,
            is_hub=profile.entity.is_hub,
        )
        if profile.entity
        else None,
        watch=to_out(profile.watch) if profile.watch else None,
        community_id=profile.community_id,
        snapshot_at=profile.snapshot_at,
        summary=profile.summary,
        tags=[LabelOut.model_validate(x) for x in profile.labels if x.kind == LabelKind.TAG],
        cluster=first(LabelKind.CLUSTER),
        anomaly=first(LabelKind.ANOMALY),
        drift=first(LabelKind.DRIFT),
    )


@router.get("/{address}/features", response_model=list[FeatureSnapshotOut])
def get_features(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    window: Window = "all",
    history: Annotated[int, Query(ge=1, le=100, description="Number of snapshots")] = 1,
) -> list[FeatureSnapshotOut]:
    snapshots = snapshot_history(session, chain.chain_id, address, window, history)
    return [FeatureSnapshotOut.model_validate(s) for s in snapshots]


@router.get("/{address}/transfers", response_model=Page[TransferOut])
def get_transfers(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    limit: LimitDep,
    offset: OffsetDep = 0,
    include_spam: bool = False,
) -> Page[TransferOut]:
    total, rows = wallet_transfers(
        session, chain.chain_id, address, include_spam=include_spam, limit=limit, offset=offset
    )
    return Page(
        total=total,
        limit=limit,
        offset=offset,
        items=[TransferOut.model_validate(r) for r in rows],
    )


@router.get("/{address}/trades", response_model=Page[TradeOut])
def get_trades(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    limit: LimitDep,
    offset: OffsetDep = 0,
) -> Page[TradeOut]:
    """DEX swaps this wallet signed, newest first."""
    total, rows = wallet_trades(session, chain.chain_id, address, limit=limit, offset=offset)
    return Page(
        total=total,
        limit=limit,
        offset=offset,
        items=[TradeOut(**r.__dict__) for r in rows],
    )


@router.get("/{address}/timeline", response_model=list[TimelineBucketOut])
def get_timeline(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    bucket: Literal["day", "week", "month"] = "week",
    days: Annotated[int, Query(ge=1, le=3650)] = 365,
) -> list[TimelineBucketOut]:
    rows = wallet_timeline(session, chain.chain_id, address, bucket=bucket, days=days)
    return [TimelineBucketOut(**r.__dict__) for r in rows]


@router.get("/{address}/neighbors", response_model=NetworkOut)
def get_neighbors(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    min_tx: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> NetworkOut:
    network = ego_network(session, chain.chain_id, address, depth=depth, min_tx=min_tx, limit=limit)
    return NetworkOut(
        center=network.center,
        nodes=[NodeOut(**n.__dict__) for n in network.nodes],
        edges=[EdgeOut(**e.__dict__) for e in network.edges],
    )


@router.get("/{address}/similar", response_model=list[SimilarWalletOut])
def get_similar(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    window: Window = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[SimilarWalletOut]:
    result = similar_wallets(session, chain.chain_id, address, window=window, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="no feature snapshot for this wallet yet")
    return [SimilarWalletOut(**s.__dict__) for s in result]


@router.get("/{address}/heatmap", response_model=HeatmapOut)
def get_heatmap(
    address: AddressDep,
    session: SessionDep,
    chain: ChainDep,
    days: Annotated[int, Query(ge=1, le=3650)] = 365,
) -> HeatmapOut:
    heatmap = wallet_activity_heatmap(session, chain.chain_id, address, days=days)
    return HeatmapOut(**heatmap.__dict__)
