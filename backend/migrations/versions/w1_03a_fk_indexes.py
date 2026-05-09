"""Wave 1: add missing foreign key indexes.

Revision ID: w1_03a
Revises: w1_02a
"""

from alembic import op

revision = "w1_03a"
down_revision = "w1_02a"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_subscriptions_customer_id", "subscriptions", "customer_id"),
    ("ix_subscriptions_prepay_invoice_id", "subscriptions", "prepay_invoice_id"),
    ("ix_webhook_deliveries_invoice_id", "webhook_deliveries", "invoice_id"),
    ("ix_subscription_payments_invoice_id", "subscription_payments", "invoice_id"),
    ("ix_webhook_dead_letters_delivery_id", "webhook_dead_letters", "delivery_id"),
    ("ix_subscription_renewal_events_invoice_id", "subscription_renewal_events", "invoice_id"),
)


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for name, table, column in INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({column})")


def downgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for name, _, _ in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
