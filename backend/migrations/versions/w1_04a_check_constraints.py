"""Wave 1: add numeric and temporal check constraints.

Revision ID: w1_04a
Revises: w1_03a
"""

from alembic import op

revision = "w1_04a"
down_revision = "w1_03a"
branch_labels = None
depends_on = None

CHECKS = (
    ("payments", "ck_payments_amount_atomic_nonnegative", "amount_atomic >= 0"),
    ("payments", "ck_payments_confirmations_nonnegative", "confirmations >= 0"),
    ("invoices", "ck_invoices_amount_atomic_positive", "amount_atomic > 0"),
    ("subscriptions", "ck_subscriptions_amount_atomic_positive", "amount_atomic > 0"),
    ("subscriptions", "ck_subscriptions_interval_days_positive", "interval_days > 0"),
    ("subscriptions", "ck_subscriptions_grace_days_soft_nonnegative", "grace_days_soft >= 0"),
    ("subscriptions", "ck_subscriptions_grace_days_hard_nonnegative", "grace_days_hard >= 0"),
    ("subscriptions", "ck_subscriptions_grace_days_order", "grace_days_hard >= grace_days_soft"),
    ("subscriptions", "ck_subscriptions_trial_days_positive", "trial_days IS NULL OR trial_days > 0"),
    ("subscription_payments", "ck_subscription_payments_period_order", "period_end > period_start"),
    ("webhook_deliveries", "ck_webhook_deliveries_attempts_nonnegative", "attempts >= 0"),
    ("webhook_dead_letters", "ck_webhook_dead_letters_retry_count_nonnegative", "retry_count >= 0"),
)


def upgrade() -> None:
    for table, name, expression in CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(name, table, type_="check")
