"""price misses and unpriced transfer index

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNPRICED = "amount_usd IS NULL AND normalized_at IS NOT NULL AND NOT is_spam"


def upgrade() -> None:
    op.alter_column("token_prices", "price_usd", existing_type=sa.Numeric(), nullable=True)
    op.create_index(
        "ix_transfers_unpriced",
        "transfers",
        ["chain_id", "id"],
        unique=False,
        postgresql_where=sa.text(UNPRICED),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transfers_unpriced", table_name="transfers", postgresql_where=sa.text(UNPRICED)
    )
    op.execute("DELETE FROM token_prices WHERE price_usd IS NULL")
    op.alter_column("token_prices", "price_usd", existing_type=sa.Numeric(), nullable=False)
