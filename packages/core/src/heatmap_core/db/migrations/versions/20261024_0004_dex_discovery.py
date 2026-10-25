"""dex discovery

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24 21:34:27.010497
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dex_cursors",
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("last_block", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("chain_id", name=op.f("pk_dex_cursors")),
    )
    op.create_table(
        "dex_pools",
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("pool_id", sa.String(length=66), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("factory", sa.String(length=42), nullable=True),
        sa.Column("token0", sa.String(length=42), nullable=True),
        sa.Column("token1", sa.String(length=42), nullable=True),
        sa.Column("fee", sa.Integer(), nullable=True),
        sa.Column("hooks", sa.String(length=42), nullable=True),
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            comment="Known factory confirms the pool (v4: PoolId matches)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("chain_id", "pool_id", name=op.f("pk_dex_pools")),
    )
    op.create_table(
        "dex_traders",
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("first_trade_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_trade_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tx_count", sa.Integer(), nullable=False),
        sa.Column("active_days", sa.Integer(), nullable=False),
        sa.Column("volume_usd", sa.Numeric(precision=38, scale=8), nullable=True),
        sa.Column("max_tx_usd", sa.Numeric(precision=38, scale=8), nullable=True),
        sa.Column("distinct_tokens", sa.Integer(), nullable=False),
        sa.Column("protocols", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("top_tokens", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("router_share", sa.Float(), nullable=False),
        sa.Column("private_share", sa.Float(), nullable=False),
        sa.Column("settlement_share", sa.Float(), nullable=False),
        sa.Column("swaps_per_tx", sa.Float(), nullable=False),
        sa.Column(
            "arbitrage_share",
            sa.Float(),
            nullable=False,
            comment="Share of circular transactions",
        ),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("bot_reason", sa.String(length=64), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("chain_id", "address", name=op.f("pk_dex_traders")),
    )
    op.create_index(
        "ix_dex_traders_volume", "dex_traders", ["chain_id", "volume_usd"], unique=False
    )
    op.create_table(
        "dex_trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("pool_id", sa.String(length=66), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column(
            "trader", sa.String(length=42), nullable=False, comment="Transaction signer (tx.from)"
        ),
        sa.Column(
            "tx_to", sa.String(length=42), nullable=True, comment="Contract the signer called"
        ),
        sa.Column("token_in", sa.String(length=42), nullable=False),
        sa.Column("token_out", sa.String(length=42), nullable=False),
        sa.Column("amount_in_raw", sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column("amount_out_raw", sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column("amount_in", sa.Numeric(precision=78, scale=18), nullable=True),
        sa.Column("amount_out", sa.Numeric(precision=78, scale=18), nullable=True),
        sa.Column("amount_usd", sa.Numeric(precision=38, scale=8), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dex_trades")),
    )
    op.create_index("ix_dex_trades_time", "dex_trades", ["chain_id", "block_time"], unique=False)
    op.create_index(
        "ix_dex_trades_trader_time",
        "dex_trades",
        ["chain_id", "trader", "block_time"],
        unique=False,
    )
    op.create_index(
        "ix_dex_trades_unvalued",
        "dex_trades",
        ["chain_id", "id"],
        unique=False,
        postgresql_where=sa.text("amount_usd IS NULL"),
    )
    op.create_index(
        "uq_dex_trades_chain_tx_log",
        "dex_trades",
        ["chain_id", "tx_hash", "log_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_dex_trades_chain_tx_log", table_name="dex_trades")
    op.drop_index(
        "ix_dex_trades_unvalued",
        table_name="dex_trades",
        postgresql_where=sa.text("amount_usd IS NULL"),
    )
    op.drop_index("ix_dex_trades_trader_time", table_name="dex_trades")
    op.drop_index("ix_dex_trades_time", table_name="dex_trades")
    op.drop_table("dex_trades")
    op.drop_index("ix_dex_traders_volume", table_name="dex_traders")
    op.drop_table("dex_traders")
    op.drop_table("dex_pools")
    op.drop_table("dex_cursors")
