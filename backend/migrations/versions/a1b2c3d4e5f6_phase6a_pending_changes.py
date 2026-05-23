"""Phase 6A: pending changes + billing anchor

Revision ID: a1b2c3d4e5f6
Revises: 0b5457cee966
Create Date: 2026-03-26 12:00:00.000000

Changes:
- Add pending_amount_atomic, pending_amount_xmr columns
- Add pending_interval_days, pending_grace_soft, pending_grace_hard columns
- Add billing_anchor_at column (backfilled from created_at, then NOT NULL)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0b5457cee966"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pending changes (nullable — NULL = no pending change)
    op.add_column("subscriptions", sa.Column("pending_amount_atomic", sa.BigInteger(), nullable=True))
    op.add_column("subscriptions", sa.Column("pending_amount_xmr", sa.Numeric(18, 12), nullable=True))
    op.add_column("subscriptions", sa.Column("pending_interval_days", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("pending_grace_soft", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("pending_grace_hard", sa.Integer(), nullable=True))

    # Billing anchor — add nullable first
    op.add_column("subscriptions", sa.Column("billing_anchor_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill: set anchor = created_at for existing rows
    op.execute("UPDATE subscriptions SET billing_anchor_at = created_at WHERE billing_anchor_at IS NULL")

    # Make NOT NULL after backfill
    op.alter_column("subscriptions", "billing_anchor_at", nullable=False)


def downgrade() -> None:
    op.drop_column("subscriptions", "billing_anchor_at")
    op.drop_column("subscriptions", "pending_grace_hard")
    op.drop_column("subscriptions", "pending_grace_soft")
    op.drop_column("subscriptions", "pending_interval_days")
    op.drop_column("subscriptions", "pending_amount_xmr")
    op.drop_column("subscriptions", "pending_amount_atomic")
