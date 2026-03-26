"""Phase 6B: Webhook DLQ + cursor pagination indexes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-26 18:00:00.000000

Changes:
- Add 'dead_lettered' value to webhook_status enum
- Create webhook_dead_letters table
- Add cursor pagination indexes (6 tables)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add 'dead_lettered' to webhook_status enum
    op.execute("ALTER TYPE webhook_status ADD VALUE 'dead_lettered' AFTER 'failed'")

    # 2. Create webhook_dead_letters table
    op.create_table(
        "webhook_dead_letters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("delivery_id", UUID(as_uuid=True),
                  sa.ForeignKey("webhook_deliveries.id"), nullable=False),
        sa.Column("merchant_id", UUID(as_uuid=True),
                  sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("original_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # DLQ index: merchant + resolved + dead_lettered_at
    op.create_index(
        "idx_dlq_merchant",
        "webhook_dead_letters",
        ["merchant_id", "resolved", sa.text("dead_lettered_at DESC")],
    )

    # 3. Cursor pagination indexes (6 tables)
    for table in ["invoices", "customers", "subscriptions",
                  "webhook_deliveries", "api_keys"]:
        op.create_index(
            f"idx_{table}_cursor",
            table,
            ["merchant_id", sa.text("created_at DESC"), sa.text("id DESC")],
        )

    # payments: cursor via invoice join — index on (invoice_id, detected_at, id)
    op.create_index(
        "idx_payments_cursor",
        "payments",
        ["invoice_id", sa.text("detected_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    # Drop cursor indexes
    op.drop_index("idx_payments_cursor", table_name="payments")
    for table in ["invoices", "customers", "subscriptions",
                  "webhook_deliveries", "api_keys"]:
        op.drop_index(f"idx_{table}_cursor", table_name=table)

    op.drop_index("idx_dlq_merchant", table_name="webhook_dead_letters")
    op.drop_table("webhook_dead_letters")

    # Note: PostgreSQL cannot remove enum values in downgrade
    # 'dead_lettered' will remain in enum but be unused
