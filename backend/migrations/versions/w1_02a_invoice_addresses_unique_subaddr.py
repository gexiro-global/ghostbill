"""Wave 1: unique invoice subaddress coordinates.

Revision ID: w1_02a
Revises: w1_01a
"""

from alembic import op

revision = "w1_02a"
down_revision = "w1_01a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_invoice_addresses_index_unique ON invoice_addresses (account_index, address_index)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_invoice_addresses_index")

    op.execute("ALTER INDEX ix_invoice_addresses_index_unique RENAME TO ix_invoice_addresses_index")


def downgrade() -> None:
    op.execute("ALTER INDEX ix_invoice_addresses_index RENAME TO ix_invoice_addresses_index_unique")
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_invoice_addresses_index ON invoice_addresses (account_index, address_index)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_invoice_addresses_index_unique")
