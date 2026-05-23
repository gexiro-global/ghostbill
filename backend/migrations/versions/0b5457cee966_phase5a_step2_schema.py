"""Phase 5A step 2: subscription schema updates

Revision ID: 0b5457cee966
Revises: 0b5457cee965
Create Date: 2026-02-13 11:16:00.000000

Changes:
- Add metadata_json JSONB column to subscriptions
- Add UNIQUE constraint on subscription_payments(subscription_id, period_start)
- Add partial index on subscriptions(next_due_at) for renewer performance
- Add index on subscription_payments(subscription_id)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0b5457cee966"
down_revision: Union[str, None] = "0b5457cee965"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add metadata_json column to subscriptions
    op.add_column(
        "subscriptions",
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )

    # 2. UNIQUE constraint on subscription_payments(subscription_id, period_start)
    # Critical for renewal idempotency — prevents double billing
    op.create_unique_constraint(
        "uq_subscription_payments_sub_period",
        "subscription_payments",
        ["subscription_id", "period_start"],
    )

    # 3. Partial index on subscriptions(next_due_at) for renewer sweep performance
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_next_due_active "
        "ON subscriptions (next_due_at) "
        "WHERE status IN ('active', 'past_due')"
    )

    # 4. Index on subscription_payments(subscription_id) for JOIN performance
    op.create_index(
        "ix_subscription_payments_subscription_id",
        "subscription_payments",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_payments_subscription_id", table_name="subscription_payments")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_next_due_active")
    op.drop_constraint("uq_subscription_payments_sub_period", "subscription_payments", type_="unique")
    op.drop_column("subscriptions", "metadata_json")
