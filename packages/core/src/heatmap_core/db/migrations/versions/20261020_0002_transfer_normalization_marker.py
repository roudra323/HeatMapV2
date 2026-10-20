"""transfer normalization marker

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 13:48:22.592928
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transfers",
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set once amounts, USD value and spam flags are computed",
        ),
    )
    op.create_index(
        "ix_transfers_pending_normalize",
        "transfers",
        ["chain_id", "id"],
        unique=False,
        postgresql_where=sa.text("normalized_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transfers_pending_normalize",
        table_name="transfers",
        postgresql_where=sa.text("normalized_at IS NULL"),
    )
    op.drop_column("transfers", "normalized_at")
