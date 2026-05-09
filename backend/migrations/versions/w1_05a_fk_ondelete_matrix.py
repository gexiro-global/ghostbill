"""Wave 1: make foreign key on-delete policy explicit.

Revision ID: w1_05a
Revises: w1_04a
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "w1_05a"
down_revision = "w1_04a"
branch_labels = None
depends_on = None

# Tuple format: (table, columns, ref_table, ref_columns, ondelete, new_name, original_name)
# original_name = PostgreSQL default convention <table>_<col>_fkey, used to restore
# exact pre-Wave-1 schema state on downgrade.
FK_CHANGES = (
    (
        "invoice_addresses",
        ("invoice_id",),
        "invoices",
        ("id",),
        "CASCADE",
        "fk_invoice_addresses_invoice_id_invoices",
        "invoice_addresses_invoice_id_fkey",
    ),
    (
        "audit_log",
        ("merchant_id",),
        "merchants",
        ("id",),
        "SET NULL",
        "fk_audit_log_merchant_id_merchants",
        "audit_log_merchant_id_fkey",
    ),
    (
        "api_keys",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_api_keys_merchant_id_merchants",
        "api_keys_merchant_id_fkey",
    ),
    (
        "customers",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_customers_merchant_id_merchants",
        "customers_merchant_id_fkey",
    ),
    (
        "invoices",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_invoices_merchant_id_merchants",
        "invoices_merchant_id_fkey",
    ),
    (
        "payments",
        ("invoice_id",),
        "invoices",
        ("id",),
        "RESTRICT",
        "fk_payments_invoice_id_invoices",
        "payments_invoice_id_fkey",
    ),
    (
        "subscription_payments",
        ("subscription_id",),
        "subscriptions",
        ("id",),
        "RESTRICT",
        "fk_subscription_payments_subscription_id_subscriptions",
        "subscription_payments_subscription_id_fkey",
    ),
    (
        "subscription_payments",
        ("invoice_id",),
        "invoices",
        ("id",),
        "RESTRICT",
        "fk_subscription_payments_invoice_id_invoices",
        "subscription_payments_invoice_id_fkey",
    ),
    (
        "subscription_renewal_events",
        ("invoice_id",),
        "invoices",
        ("id",),
        "RESTRICT",
        "fk_subscription_renewal_events_invoice_id_invoices",
        "subscription_renewal_events_invoice_id_fkey",
    ),
    (
        "subscriptions",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_subscriptions_merchant_id_merchants",
        "subscriptions_merchant_id_fkey",
    ),
    (
        "subscriptions",
        ("customer_id",),
        "customers",
        ("id",),
        "RESTRICT",
        "fk_subscriptions_customer_id_customers",
        "subscriptions_customer_id_fkey",
    ),
    (
        "subscriptions",
        ("prepay_invoice_id",),
        "invoices",
        ("id",),
        "RESTRICT",
        "fk_subscriptions_prepay_invoice_id_invoices",
        "subscriptions_prepay_invoice_id_fkey",
    ),
    (
        "wallet_shards",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_wallet_shards_merchant_id_merchants",
        "wallet_shards_merchant_id_fkey",
    ),
    (
        "webhook_deliveries",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_webhook_deliveries_merchant_id_merchants",
        "webhook_deliveries_merchant_id_fkey",
    ),
    (
        "webhook_deliveries",
        ("invoice_id",),
        "invoices",
        ("id",),
        "RESTRICT",
        "fk_webhook_deliveries_invoice_id_invoices",
        "webhook_deliveries_invoice_id_fkey",
    ),
    (
        "webhook_dead_letters",
        ("merchant_id",),
        "merchants",
        ("id",),
        "RESTRICT",
        "fk_webhook_dead_letters_merchant_id_merchants",
        "webhook_dead_letters_merchant_id_fkey",
    ),
    (
        "webhook_dead_letters",
        ("delivery_id",),
        "webhook_deliveries",
        ("id",),
        "RESTRICT",
        "fk_webhook_dead_letters_delivery_id_webhook_deliveries",
        "webhook_dead_letters_delivery_id_fkey",
    ),
)


def _existing_fk_name(table: str, columns: tuple, ref_table: str) -> str:
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_class refrel ON refrel.oid = con.confrelid
            WHERE con.contype = 'f'
              AND rel.relname = :table_name
              AND refrel.relname = :ref_table_name
              AND (
                SELECT array_agg(att.attname::text ORDER BY ord.n)
                FROM unnest(con.conkey) WITH ORDINALITY AS ord(attnum, n)
                JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
              ) = CAST(:columns AS text[])
            """
        ),
        {"table_name": table, "ref_table_name": ref_table, "columns": list(columns)},
    ).scalar()


def _replace_fk(table: str, columns: tuple, ref_table: str, ref_columns: tuple, ondelete: str, name: str) -> None:
    existing = _existing_fk_name(table, columns, ref_table)
    if existing is not None:
        op.drop_constraint(existing, table, type_="foreignkey")
    op.create_foreign_key(
        name,
        table,
        ref_table,
        list(columns),
        list(ref_columns),
        ondelete=ondelete,
        postgresql_not_valid=True,
    )
    op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    op.alter_column("audit_log", "merchant_id", existing_type=UUID(as_uuid=True), nullable=True)
    for table, columns, ref_table, ref_columns, ondelete, name, _original in FK_CHANGES:
        _replace_fk(table, columns, ref_table, ref_columns, ondelete, name)


def downgrade() -> None:
    # Restore exact pre-Wave-1 FK names with NO ACTION (default) ondelete behavior.
    for table, columns, ref_table, ref_columns, _ondelete, new_name, original_name in reversed(FK_CHANGES):
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(
            original_name,
            table,
            ref_table,
            list(columns),
            list(ref_columns),
            postgresql_not_valid=True,
        )
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {original_name}")
