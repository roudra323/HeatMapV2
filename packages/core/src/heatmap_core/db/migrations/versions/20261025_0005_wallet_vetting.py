"""wallet vetting: sent transaction counts, traded tokens, EIP-7702 reclassification

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column(
            "sent_txs",
            sa.BigInteger(),
            nullable=True,
            comment="Transactions sent (the nonce) when checked before automatic tracking",
        ),
    )
    op.add_column(
        "dex_traders",
        sa.Column(
            "traded_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Distinct tokens besides stablecoins; ETH and WETH count as one",
        ),
    )
    op.alter_column("dex_traders", "traded_tokens", server_default=None)
    # EIP-7702 delegated EOAs carry code, so they were stored as contracts, and
    # senders of internal transfers were assumed to be contracts. Check again.
    op.execute("UPDATE wallets SET kind = 'unknown' WHERE kind = 'contract'")


def downgrade() -> None:
    op.drop_column("dex_traders", "traded_tokens")
    op.drop_column("wallets", "sent_txs")
