"""Transfers, tokens and prices."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from heatmap_core.db.base import Address, Base, TimestampMixin, TokenAmount, Uint256, Usd
from heatmap_core.primitives import TokenCategory


class Token(TimestampMixin, Base):
    __tablename__ = "tokens"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[Address] = mapped_column(primary_key=True)
    standard: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(256))
    decimals: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(32), default=TokenCategory.OTHER)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False)
    spam_reason: Mapped[str | None] = mapped_column(String(128))
    price_id: Mapped[str | None] = mapped_column(String(64), comment="Price source id")


class Transfer(Base):
    """One value movement. ``uid`` is provider independent so failover never duplicates."""

    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(Integer)
    uid: Mapped[str] = mapped_column(String(80))
    tx_hash: Mapped[str] = mapped_column(String(66))
    block_number: Mapped[int] = mapped_column(BigInteger)
    block_time: Mapped[datetime]
    category: Mapped[str] = mapped_column(String(16))
    from_address: Mapped[Address]
    to_address: Mapped[Address]
    token_address: Mapped[Address]
    token_id: Mapped[str | None] = mapped_column(String(80))
    raw_amount: Mapped[Uint256]
    amount: Mapped[TokenAmount | None]
    amount_usd: Mapped[Usd | None]
    log_index: Mapped[int | None] = mapped_column(Integer)
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False)
    spam_reason: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32))
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    normalized_at: Mapped[datetime | None] = mapped_column(
        comment="Set once amounts, USD value and spam flags are computed"
    )

    __table_args__ = (
        Index("uq_transfers_chain_uid", "chain_id", "uid", unique=True),
        Index("ix_transfers_from_time", "chain_id", "from_address", "block_time"),
        Index("ix_transfers_to_time", "chain_id", "to_address", "block_time"),
        Index("ix_transfers_tx", "chain_id", "tx_hash"),
        Index("ix_transfers_token", "chain_id", "token_address"),
        Index("ix_transfers_block", "chain_id", "block_number"),
        Index(
            "ix_transfers_pending_normalize",
            "chain_id",
            "id",
            postgresql_where=text("normalized_at IS NULL"),
        ),
        Index(
            "ix_transfers_unpriced",
            "chain_id",
            "id",
            postgresql_where=text(
                "amount_usd IS NULL AND normalized_at IS NOT NULL AND NOT is_spam"
            ),
        ),
    )


class TokenPrice(Base):
    """Daily USD price. A NULL price records that ``source`` had none for that day."""

    __tablename__ = "token_prices"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_address: Mapped[Address] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    price_usd: Mapped[Decimal | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(32))
