"""Wave 1: add DLQ retry delivery plumbing column.

Revision ID: w1_06a
Revises: w1_05a
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "w1_06a"
down_revision = "w1_05a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("webhook_dead_letters", sa.Column("retry_delivery_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_webhook_dead_letters_retry_delivery_id_webhook_deliveries",
        "webhook_dead_letters",
        "webhook_deliveries",
        ["retry_delivery_id"],
        ["id"],
        ondelete="SET NULL",
        postgresql_not_valid=True,
    )
    op.execute(
        "ALTER TABLE webhook_dead_letters "
        "VALIDATE CONSTRAINT fk_webhook_dead_letters_retry_delivery_id_webhook_deliveries"
    )
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_webhook_dead_letters_retry_delivery ON webhook_dead_letters (retry_delivery_id)"
        )


def downgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_webhook_dead_letters_retry_delivery")
    op.drop_constraint(
        "fk_webhook_dead_letters_retry_delivery_id_webhook_deliveries",
        "webhook_dead_letters",
        type_="foreignkey",
    )
    op.drop_column("webhook_dead_letters", "retry_delivery_id")
