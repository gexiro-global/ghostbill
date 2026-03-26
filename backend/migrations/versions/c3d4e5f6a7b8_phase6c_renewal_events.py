"""Phase 6C: Subscription renewal events table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-26 20:00:00.000000

Changes:
- Create subscription_renewal_events table for renewal audit trail
- Index on (subscription_id, created_at DESC) for cursor pagination
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_renewal_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("subscription_id", UUID(as_uuid=True),
                  sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column("invoice_id", UUID(as_uuid=True),
                  sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "idx_renewal_events_sub",
        "subscription_renewal_events",
        ["subscription_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_renewal_events_sub",
                  table_name="subscription_renewal_events")
    op.drop_table("subscription_renewal_events")
