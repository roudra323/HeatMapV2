"""DEX pools, swaps and the traders discovered from them."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from heatmap_core.db.base import Address, Base, TimestampMixin, TokenAmount, Uint256, Usd


class DexPool(TimestampMixin, Base):
    """A pool seen emitting swaps. ``pool_id`` is the pool address, or the PoolId for v4."""

    __tablename__ = "dex_pools"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pool_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    protocol: Mapped[str] = mapped_column(String(32))
    factory: Mapped[str | None] = mapped_column(String(42))
    token0: Mapped[str | None] = mapped_column(String(42))
    token1: Mapped[str | None] = mapped_column(String(42))
    fee: Mapped[int | None] = mapped_column(Integer)
    hooks: Mapped[str | None] = mapped_column(String(42))
    verified: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Known factory confirms the pool (v4: PoolId matches)"
    )


class DexTrade(Base):
    """One swap event, attributed to the transaction signer."""

    __tablename__ = "dex_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(Integer)
    block_number: Mapped[int] = mapped_column(BigInteger)
    block_time: Mapped[datetime]
    tx_hash: Mapped[str] = mapped_column(String(66))
    log_index: Mapped[int] = mapped_column(Integer)
    pool_id: Mapped[str] = mapped_column(String(66))
    protocol: Mapped[str] = mapped_column(String(32))
    trader: Mapped[Address] = mapped_column(comment="Transaction signer (tx.from)")
    tx_to: Mapped[str | None] = mapped_column(String(42), comment="Contract the signer called")
    token_in: Mapped[Address]
    token_out: Mapped[Address]
    amount_in_raw: Mapped[Uint256]
    amount_out_raw: Mapped[Uint256]
    amount_in: Mapped[TokenAmount | None]
    amount_out: Mapped[TokenAmount | None]
    amount_usd: Mapped[Usd | None]

    __table_args__ = (
        Index("uq_dex_trades_chain_tx_log", "chain_id", "tx_hash", "log_index", unique=True),
        Index("ix_dex_trades_trader_time", "chain_id", "trader", "block_time"),
        Index("ix_dex_trades_time", "chain_id", "block_time"),
        Index(
            "ix_dex_trades_unvalued", "chain_id", "id", postgresql_where=text("amount_usd IS NULL")
        ),
    )


class DexCursor(Base):
    """Highest block whose swaps are stored."""

    __tablename__ = "dex_cursors"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_block: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class DexTrader(Base):
    """Trading statistics per signer over the discovery window, with a bot verdict."""

    __tablename__ = "dex_traders"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    first_trade_at: Mapped[datetime]
    last_trade_at: Mapped[datetime]
    tx_count: Mapped[int] = mapped_column(Integer)
    active_days: Mapped[int] = mapped_column(Integer)
    volume_usd: Mapped[Usd | None]
    max_tx_usd: Mapped[Usd | None]
    distinct_tokens: Mapped[int] = mapped_column(Integer)
    traded_tokens: Mapped[int] = mapped_column(
        Integer, comment="Distinct tokens besides stablecoins; ETH and WETH count as one"
    )
    protocols: Mapped[list[str]] = mapped_column(JSONB)
    top_tokens: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    router_share: Mapped[float] = mapped_column(Float)
    private_share: Mapped[float] = mapped_column(Float)
    settlement_share: Mapped[float] = mapped_column(Float)
    swaps_per_tx: Mapped[float] = mapped_column(Float)
    arbitrage_share: Mapped[float] = mapped_column(Float, comment="Share of circular transactions")
    is_bot: Mapped[bool] = mapped_column(Boolean)
    bot_reason: Mapped[str | None] = mapped_column(String(64))
    computed_at: Mapped[datetime]

    __table_args__ = (Index("ix_dex_traders_volume", "chain_id", "volume_usd"),)
