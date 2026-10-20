"""Read-side queries used by the API (kept here so they are testable without HTTP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from heatmap_core.db.models import (
    EntityLabel,
    SyncCursor,
    Transfer,
    Wallet,
    WalletCommunity,
    WalletFeatureSnapshot,
    WalletLabel,
    WatchlistEntry,
)
from heatmap_core.models.matrix import build_matrix
from heatmap_core.primitives import LabelKind


@dataclass
class WatchStatus:
    entry: WatchlistEntry
    last_block: int | None
    last_synced_at: datetime | None
    last_error: str | None


@dataclass
class WalletProfile:
    address: str
    wallet: Wallet | None
    entity: EntityLabel | None
    watch: WatchStatus | None
    community_id: int | None
    snapshot_at: datetime | None
    summary: dict[str, Any] = field(default_factory=dict)
    labels: list[WalletLabel] = field(default_factory=list)


SUMMARY_FEATURES = (
    "transfer_count",
    "tx_count",
    "active_days",
    "lifespan_days",
    "days_since_last",
    "volume_usd",
    "netflow_usd",
    "degree",
    "distinct_tokens",
    "share_stablecoin",
    "share_nft",
    "share_cex",
    "share_dex_router",
    "funder_cluster_size",
    "max_counterparty_jaccard",
    "most_similar_wallet",
)


def watch_statuses(
    session: Session,
    chain_id: int,
    *,
    origin: str | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[WatchStatus]]:
    conditions = [WatchlistEntry.chain_id == chain_id]
    if origin is not None:
        conditions.append(WatchlistEntry.origin == origin)
    if active is not None:
        conditions.append(WatchlistEntry.active.is_(active))
    total = session.scalar(select(func.count()).select_from(WatchlistEntry).where(*conditions))
    rows = session.execute(
        select(WatchlistEntry, SyncCursor)
        .outerjoin(
            SyncCursor,
            and_(
                SyncCursor.chain_id == WatchlistEntry.chain_id,
                SyncCursor.address == WatchlistEntry.address,
            ),
        )
        .where(*conditions)
        .order_by(WatchlistEntry.hop, WatchlistEntry.priority, WatchlistEntry.address)
        .limit(limit)
        .offset(offset)
    )
    statuses = [
        WatchStatus(
            entry=entry,
            last_block=cursor.last_block if cursor else None,
            last_synced_at=cursor.last_synced_at if cursor else None,
            last_error=cursor.last_error if cursor else None,
        )
        for entry, cursor in rows
    ]
    return int(total or 0), statuses


def latest_snapshot(
    session: Session, chain_id: int, address: str, window: str
) -> WalletFeatureSnapshot | None:
    return session.scalars(
        select(WalletFeatureSnapshot)
        .where(
            WalletFeatureSnapshot.chain_id == chain_id,
            WalletFeatureSnapshot.address == address,
            WalletFeatureSnapshot.window == window,
        )
        .order_by(WalletFeatureSnapshot.snapshot_at.desc())
        .limit(1)
    ).first()


def snapshot_history(
    session: Session, chain_id: int, address: str, window: str, limit: int
) -> list[WalletFeatureSnapshot]:
    return list(
        session.scalars(
            select(WalletFeatureSnapshot)
            .where(
                WalletFeatureSnapshot.chain_id == chain_id,
                WalletFeatureSnapshot.address == address,
                WalletFeatureSnapshot.window == window,
            )
            .order_by(WalletFeatureSnapshot.snapshot_at.desc())
            .limit(limit)
        )
    )


def latest_labels(session: Session, chain_id: int, address: str) -> list[WalletLabel]:
    """Labels from the most recent model run that covered this wallet."""
    latest = session.scalar(
        select(func.max(WalletLabel.snapshot_at)).where(
            WalletLabel.chain_id == chain_id, WalletLabel.address == address
        )
    )
    if latest is None:
        return []
    return list(
        session.scalars(
            select(WalletLabel)
            .where(
                WalletLabel.chain_id == chain_id,
                WalletLabel.address == address,
                WalletLabel.snapshot_at == latest,
            )
            .order_by(WalletLabel.kind, WalletLabel.score.desc().nulls_last())
        )
    )


def wallet_profile(
    session: Session, chain_id: int, address: str, window: str = "all"
) -> WalletProfile | None:
    wallet = session.get(Wallet, (chain_id, address))
    entity = session.get(EntityLabel, (chain_id, address))
    entry = session.get(WatchlistEntry, (chain_id, address))
    if wallet is None and entity is None and entry is None:
        return None
    cursor = session.get(SyncCursor, (chain_id, address))
    community = session.get(WalletCommunity, (chain_id, address))
    snapshot = latest_snapshot(session, chain_id, address, window)
    features = snapshot.features if snapshot else {}
    return WalletProfile(
        address=address,
        wallet=wallet,
        entity=entity,
        watch=WatchStatus(
            entry,
            cursor.last_block if cursor else None,
            cursor.last_synced_at if cursor else None,
            cursor.last_error if cursor else None,
        )
        if entry
        else None,
        community_id=community.community_id if community else None,
        snapshot_at=snapshot.snapshot_at if snapshot else None,
        summary={k: features[k] for k in SUMMARY_FEATURES if k in features},
        labels=latest_labels(session, chain_id, address),
    )


def wallet_transfers(
    session: Session,
    chain_id: int,
    address: str,
    *,
    include_spam: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Transfer]]:
    conditions = [
        Transfer.chain_id == chain_id,
        or_(Transfer.from_address == address, Transfer.to_address == address),
    ]
    if not include_spam:
        conditions.append(Transfer.is_spam.is_(False))
    total = session.scalar(select(func.count()).select_from(Transfer).where(*conditions))
    rows = session.scalars(
        select(Transfer)
        .where(*conditions)
        .order_by(Transfer.block_number.desc(), Transfer.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return int(total or 0), list(rows)


@dataclass
class TimelineBucket:
    period: datetime
    transfers_in: int
    transfers_out: int
    usd_in: Decimal | None
    usd_out: Decimal | None
    counterparties: int


TIMELINE_SQL = text(
    """
    SELECT date_trunc(:bucket, block_time) AS period,
           COUNT(*) FILTER (WHERE to_address = :address) AS transfers_in,
           COUNT(*) FILTER (WHERE from_address = :address) AS transfers_out,
           SUM(amount_usd) FILTER (WHERE to_address = :address) AS usd_in,
           SUM(amount_usd) FILTER (WHERE from_address = :address) AS usd_out,
           COUNT(DISTINCT CASE WHEN from_address = :address THEN to_address
                               ELSE from_address END) AS counterparties
    FROM transfers
    WHERE chain_id = :chain_id AND NOT is_spam AND block_time >= :since
      AND (from_address = :address OR to_address = :address)
    GROUP BY 1
    ORDER BY 1
    """
)


def wallet_timeline(
    session: Session, chain_id: int, address: str, *, bucket: str, days: int
) -> list[TimelineBucket]:
    if bucket not in {"day", "week", "month"}:
        raise ValueError("bucket must be day, week or month")
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.execute(
        TIMELINE_SQL,
        {"bucket": bucket, "address": address, "chain_id": chain_id, "since": since},
    )
    return [TimelineBucket(**dict(r._mapping)) for r in rows]


@dataclass
class ClusterSummary:
    label: str
    cluster_id: int
    size: int
    profile: str | None
    snapshot_at: datetime


def latest_model_snapshot(session: Session, chain_id: int) -> datetime | None:
    return session.scalar(
        select(func.max(WalletLabel.snapshot_at)).where(WalletLabel.chain_id == chain_id)
    )


def cluster_summaries(session: Session, chain_id: int) -> list[ClusterSummary]:
    snapshot = latest_model_snapshot(session, chain_id)
    if snapshot is None:
        return []
    rows = session.execute(
        select(WalletLabel.label, func.count(), func.min(WalletLabel.reason))
        .where(
            WalletLabel.chain_id == chain_id,
            WalletLabel.snapshot_at == snapshot,
            WalletLabel.kind == LabelKind.CLUSTER,
        )
        .group_by(WalletLabel.label)
        .order_by(func.count().desc())
    )
    return [
        ClusterSummary(
            label=label,
            cluster_id=-1 if label == "noise" else int(label.removeprefix("cluster_")),
            size=int(size),
            profile=profile,
            snapshot_at=snapshot,
        )
        for label, size, profile in rows
    ]


@dataclass
class ClusterPoint:
    address: str
    cluster_id: int
    x: float
    y: float
    probability: float | None


def cluster_points(session: Session, chain_id: int, limit: int) -> list[ClusterPoint]:
    snapshot = latest_model_snapshot(session, chain_id)
    if snapshot is None:
        return []
    labels = session.scalars(
        select(WalletLabel)
        .where(
            WalletLabel.chain_id == chain_id,
            WalletLabel.snapshot_at == snapshot,
            WalletLabel.kind == LabelKind.CLUSTER,
        )
        .order_by(WalletLabel.address)
        .limit(limit)
    )
    return [
        ClusterPoint(
            address=label.address,
            cluster_id=int((label.details or {}).get("cluster_id", -1)),
            x=float((label.details or {}).get("x", 0.0)),
            y=float((label.details or {}).get("y", 0.0)),
            probability=label.score,
        )
        for label in labels
    ]


def tag_counts(session: Session, chain_id: int) -> dict[str, int]:
    snapshot = latest_model_snapshot(session, chain_id)
    if snapshot is None:
        return {}
    rows = session.execute(
        select(WalletLabel.label, func.count())
        .where(
            WalletLabel.chain_id == chain_id,
            WalletLabel.snapshot_at == snapshot,
            WalletLabel.kind == LabelKind.TAG,
        )
        .group_by(WalletLabel.label)
        .order_by(func.count().desc())
    )
    return {label: int(n) for label, n in rows}


@dataclass
class SimilarWallet:
    address: str
    similarity: float
    shared_tags: list[str]


def similar_wallets(
    session: Session, chain_id: int, address: str, *, window: str = "all", limit: int = 10
) -> list[SimilarWallet] | None:
    """Wallets whose latest behaviour vector is closest (cosine) to ``address``."""
    snapshot_at = session.scalar(
        select(func.max(WalletFeatureSnapshot.snapshot_at)).where(
            WalletFeatureSnapshot.chain_id == chain_id, WalletFeatureSnapshot.window == window
        )
    )
    if snapshot_at is None:
        return None
    rows = list(
        session.execute(
            select(WalletFeatureSnapshot.address, WalletFeatureSnapshot.features).where(
                WalletFeatureSnapshot.chain_id == chain_id,
                WalletFeatureSnapshot.window == window,
                WalletFeatureSnapshot.snapshot_at == snapshot_at,
            )
        )
    )
    addresses = [a for a, _ in rows]
    if address not in addresses:
        return None
    matrix = build_matrix(addresses, [f for _, f in rows])
    vectors = matrix.scaled
    norms = np.linalg.norm(vectors, axis=1)
    norms[norms == 0] = 1.0
    target = addresses.index(address)
    similarity = vectors @ vectors[target] / (norms * norms[target])
    order = [i for i in np.argsort(-similarity) if i != target][:limit]

    tags_by_wallet: dict[str, set[str]] = {}
    for wallet, tag in session.execute(
        select(WalletLabel.address, WalletLabel.label).where(
            WalletLabel.chain_id == chain_id,
            WalletLabel.kind == LabelKind.TAG,
            WalletLabel.snapshot_at == snapshot_at,
            WalletLabel.address.in_([addresses[i] for i in order] + [address]),
        )
    ):
        tags_by_wallet.setdefault(wallet, set()).add(tag)
    own = tags_by_wallet.get(address, set())
    return [
        SimilarWallet(
            address=addresses[i],
            similarity=round(float(similarity[i]), 4),
            shared_tags=sorted(own & tags_by_wallet.get(addresses[i], set())),
        )
        for i in order
    ]
