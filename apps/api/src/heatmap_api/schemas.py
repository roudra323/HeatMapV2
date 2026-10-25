"""Response and request models (the API contract; the web client is generated from it)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Page[T](BaseModel):
    total: int
    limit: int
    offset: int
    items: list[T]


class ChainOut(BaseModel):
    name: str
    chain_id: int
    native_symbol: str
    explorer_url: str | None


class WatchlistCreate(BaseModel):
    address: str = Field(examples=["0xd8da6bf26964af9d7eed9e03e53415d37aa96045"])
    priority: int = Field(100, ge=0, le=10_000)
    note: str | None = Field(None, max_length=500)


class WatchlistEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    address: str
    origin: str
    hop: int
    via_address: str | None
    priority: int
    active: bool
    note: str | None
    created_at: datetime
    last_block: int | None = None
    last_synced_at: datetime | None = None
    last_error: str | None = None


class EntityOut(BaseModel):
    name: str
    category: str
    is_hub: bool


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    label: str
    score: float | None
    reason: str | None
    window: str
    snapshot_at: datetime
    model_version: str
    details: dict[str, Any] | None


class WalletProfileOut(BaseModel):
    address: str
    kind: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    funded_by: str | None
    entity: EntityOut | None
    watch: WatchlistEntryOut | None
    community_id: int | None
    snapshot_at: datetime | None
    summary: dict[str, Any]
    tags: list[LabelOut]
    cluster: LabelOut | None
    anomaly: LabelOut | None
    drift: LabelOut | None


class FeatureSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    window: str
    snapshot_at: datetime
    feature_version: str
    transfer_count: int
    volume_usd: Decimal | None
    features: dict[str, Any]


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tx_hash: str
    block_number: int
    block_time: datetime
    category: str
    from_address: str
    to_address: str
    token_address: str
    token_id: str | None
    amount: Decimal | None
    amount_usd: Decimal | None
    is_spam: bool
    spam_reason: str | None


class TimelineBucketOut(BaseModel):
    period: datetime
    transfers_in: int
    transfers_out: int
    usd_in: Decimal | None
    usd_out: Decimal | None
    counterparties: int


class NodeOut(BaseModel):
    address: str
    depth: int
    label: str | None
    category: str | None
    is_hub: bool
    tracked: bool
    hop: int | None
    kind: str | None
    community_id: int | None


class EdgeOut(BaseModel):
    src: str
    dst: str
    tx_count: int
    value_usd: Decimal | None
    first_seen_at: datetime
    last_seen_at: datetime


class NetworkOut(BaseModel):
    center: str
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class SimilarWalletOut(BaseModel):
    address: str
    similarity: float
    shared_tags: list[str]


class HeatmapOut(BaseModel):
    rows: list[str]
    columns: list[str]
    values: list[list[float]]
    meta: dict[str, Any]


class ClusterOut(BaseModel):
    label: str
    cluster_id: int
    size: int
    profile: str | None
    snapshot_at: datetime


class ClusterPointOut(BaseModel):
    address: str
    cluster_id: int
    x: float
    y: float
    probability: float | None


class TopTokenOut(BaseModel):
    token: str
    symbol: str | None
    trades: int


class TraderOut(BaseModel):
    """A wallet found trading on DEXes, with its statistics over the discovery window."""

    address: str
    first_trade_at: datetime
    last_trade_at: datetime
    tx_count: int
    active_days: int
    volume_usd: Decimal | None
    max_tx_usd: Decimal | None
    distinct_tokens: int
    protocols: list[str]
    top_tokens: list[TopTokenOut]
    router_share: float
    private_share: float
    settlement_share: float
    swaps_per_tx: float
    arbitrage_share: float
    is_bot: bool
    bot_reason: str | None
    tracked: bool
    computed_at: datetime


class TradeOut(BaseModel):
    tx_hash: str
    block_number: int
    block_time: datetime
    log_index: int
    protocol: str
    pool_id: str
    tx_to: str | None
    token_in: str
    token_in_symbol: str | None
    amount_in: Decimal | None
    token_out: str
    token_out_symbol: str | None
    amount_out: Decimal | None
    amount_usd: Decimal | None
