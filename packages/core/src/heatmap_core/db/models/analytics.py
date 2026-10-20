"""Graph, feature snapshots and model outputs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from heatmap_core.db.base import Address, Base, Usd


class Edge(Base):
    """Directed, aggregated non-spam flow between two addresses."""

    __tablename__ = "edges"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src: Mapped[Address] = mapped_column(primary_key=True)
    dst: Mapped[Address] = mapped_column(primary_key=True)
    tx_count: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    value_usd: Mapped[Usd | None]
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_edges_dst", "chain_id", "dst"),)


class WalletCommunity(Base):
    __tablename__ = "wallet_communities"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(Integer)
    algorithm: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime]

    __table_args__ = (Index("ix_wallet_communities_community", "chain_id", "community_id"),)


class WalletFeatureSnapshot(Base):
    """Behaviour features for a wallet over a window, frozen at ``snapshot_at``.

    Features live in JSONB so the feature registry can grow without migrations;
    ``feature_version`` records which registry produced them.
    """

    __tablename__ = "wallet_features"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    window: Mapped[str] = mapped_column(String(8), primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(16))
    transfer_count: Mapped[int] = mapped_column(BigInteger)
    volume_usd: Mapped[Usd | None]
    features: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (Index("ix_wallet_features_latest", "chain_id", "window", "snapshot_at"),)


class WalletLabel(Base):
    """Output of a model: a tag, cluster, anomaly score or drift flag."""

    __tablename__ = "wallet_labels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(Integer)
    address: Mapped[Address]
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(64))
    score: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    window: Mapped[str] = mapped_column(String(8))
    snapshot_at: Mapped[datetime]
    model_version: Mapped[str] = mapped_column(String(32))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_wallet_labels_wallet", "chain_id", "address", "kind"),
        Index("ix_wallet_labels_snapshot", "chain_id", "snapshot_at", "kind"),
    )


class ProviderKeyUsage(Base):
    """Per-key daily request counters so quotas survive restarts."""

    __tablename__ = "provider_key_usage"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    request_count: Mapped[int] = mapped_column(BigInteger, default=0)
    rate_limited_count: Mapped[int] = mapped_column(BigInteger, default=0)
    error_count: Mapped[int] = mapped_column(BigInteger, default=0)


__all__ = [
    "Edge",
    "ProviderKeyUsage",
    "WalletCommunity",
    "WalletFeatureSnapshot",
    "WalletLabel",
]
