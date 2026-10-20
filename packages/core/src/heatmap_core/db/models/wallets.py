"""Tracked wallets, watchlist, sync cursors and entity labels."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from heatmap_core.db.base import Address, Base, TimestampMixin
from heatmap_core.primitives import AddressKind, WatchOrigin


class Wallet(TimestampMixin, Base):
    """Every address we have seen, tracked or not."""

    __tablename__ = "wallets"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default=AddressKind.UNKNOWN)
    first_seen_at: Mapped[datetime | None]
    last_seen_at: Mapped[datetime | None]
    funded_by: Mapped[str | None] = mapped_column(
        String(42), comment="Sender of the first inbound native transfer"
    )


class WatchlistEntry(TimestampMixin, Base):
    """Wallets whose activity is pulled on every sync."""

    __tablename__ = "watchlist"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(16), default=WatchOrigin.SEED)
    hop: Mapped[int] = mapped_column(Integer, default=0)
    via_address: Mapped[str | None] = mapped_column(String(42))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_watchlist_active_priority", "chain_id", "active", "priority"),)


class SyncCursor(Base):
    """Highest block fully ingested for a wallet."""

    __tablename__ = "sync_cursors"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    last_block: Mapped[int] = mapped_column(BigInteger, default=0)
    last_synced_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)


class EntityLabel(TimestampMixin, Base):
    """Known entities (exchanges, routers, bridges...). Hubs are never expanded."""

    __tablename__ = "entity_labels"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    is_hub: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="seed_file")
