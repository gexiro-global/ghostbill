"""Phase 8A: Trial periods — trialing enum + trial columns.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-24
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add enum value (must be outside transaction)
    op.execute("COMMIT")
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'trialing'")
    op.execute("BEGIN")

    # Step 2: Add trial columns
    op.add_column(
        "subscriptions",
        sa.Column("trial_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "trial_end_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "trial_end_at")
    op.drop_column("subscriptions", "trial_days")
    # Note: PostgreSQL does not support removing enum values
