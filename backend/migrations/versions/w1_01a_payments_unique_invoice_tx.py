"""Wave 1: unique payment transaction per invoice.

Revision ID: w1_01a
Revises: f6a7b8c9d0e1
"""

from alembic import op

revision = "w1_01a"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_payments_invoice_tx_unique ON payments (invoice_id, tx_hash)"
        )

    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT uq_payments_invoice_tx UNIQUE USING INDEX ix_payments_invoice_tx_unique"
    )


def downgrade() -> None:
    op.drop_constraint("uq_payments_invoice_tx", "payments", type_="unique")
