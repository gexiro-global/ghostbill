"""Baseline Phase 0-4 schema.

Revision ID: ff232ea503f4
Revises:
Create Date: 2026-02-12 19:52:00.000000

Creates the complete Phase 0-4 schema from scratch using raw SQL
to avoid SQLAlchemy Enum type creation conflicts with model metadata.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ff232ea503f4"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ENUMs
    conn.execute(
        sa.text(
            "CREATE TYPE invoice_status AS ENUM"
            " ('pending','paid','expired','partially_paid','overpaid','late_paid','cancelled')"
        )
    )
    conn.execute(sa.text("CREATE TYPE payment_status AS ENUM ('detected','confirmed','orphaned')"))
    conn.execute(sa.text("CREATE TYPE subscription_status AS ENUM ('active','paused','cancelled','expired')"))
    conn.execute(sa.text("CREATE TYPE webhook_status AS ENUM ('pending','delivered','failed')"))

    # merchants
    conn.execute(
        sa.text("""
        CREATE TABLE merchants (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            monero_address VARCHAR(128) NOT NULL,
            view_key_encrypted TEXT,
            webhook_url VARCHAR(2048),
            webhook_secret VARCHAR(255),
            environment VARCHAR(10) NOT NULL DEFAULT 'test',
            is_active BOOLEAN NOT NULL DEFAULT true,
            metadata_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )

    # invoices
    conn.execute(
        sa.text("""
        CREATE TABLE invoices (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            amount_atomic BIGINT NOT NULL,
            amount_xmr NUMERIC(18,12) NOT NULL,
            fiat_currency VARCHAR(3),
            fiat_amount NUMERIC(18,2),
            fiat_rate NUMERIC(18,8),
            status invoice_status NOT NULL,
            description VARCHAR(1024),
            metadata_json JSONB,
            expires_at TIMESTAMPTZ NOT NULL,
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_invoices_merchant_created ON invoices (merchant_id, created_at)"))
    conn.execute(
        sa.text(
            "CREATE INDEX ix_invoices_status_expires ON invoices (status, expires_at)"
            " WHERE status = 'pending'::invoice_status"
        )
    )

    # invoice_addresses
    conn.execute(
        sa.text("""
        CREATE TABLE invoice_addresses (
            id UUID PRIMARY KEY,
            invoice_id UUID NOT NULL REFERENCES invoices(id),
            address VARCHAR(128) NOT NULL,
            address_index INTEGER NOT NULL,
            account_index INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_invoice_addresses_index ON invoice_addresses (account_index, address_index)"))

    # payments
    conn.execute(
        sa.text("""
        CREATE TABLE payments (
            id UUID PRIMARY KEY,
            invoice_id UUID NOT NULL REFERENCES invoices(id),
            tx_hash VARCHAR(64) NOT NULL,
            amount_atomic BIGINT NOT NULL,
            amount_xmr NUMERIC(18,12) NOT NULL,
            status payment_status NOT NULL,
            confirmations INTEGER NOT NULL,
            block_height BIGINT,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            confirmed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_payments_invoice_status ON payments (invoice_id, status)"))
    conn.execute(sa.text("CREATE INDEX ix_payments_tx_hash ON payments (tx_hash)"))

    # customers
    conn.execute(
        sa.text("""
        CREATE TABLE customers (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            external_id VARCHAR(255),
            email VARCHAR(255),
            metadata_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE UNIQUE INDEX ix_customers_merchant_external ON customers (merchant_id, external_id)"))

    # subscriptions
    conn.execute(
        sa.text("""
        CREATE TABLE subscriptions (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            customer_id UUID NOT NULL REFERENCES customers(id),
            amount_atomic BIGINT NOT NULL,
            amount_xmr NUMERIC(18,12) NOT NULL,
            interval_days INTEGER NOT NULL,
            status subscription_status NOT NULL,
            grace_days_soft INTEGER NOT NULL DEFAULT 3,
            grace_days_hard INTEGER NOT NULL DEFAULT 7,
            next_due_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_subscriptions_customer_id ON subscriptions (customer_id)"))

    # subscription_payments
    conn.execute(
        sa.text("""
        CREATE TABLE subscription_payments (
            id UUID PRIMARY KEY,
            subscription_id UUID NOT NULL REFERENCES subscriptions(id),
            invoice_id UUID NOT NULL REFERENCES invoices(id),
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_subscription_payments_invoice_id ON subscription_payments (invoice_id)"))

    # wallet_shards
    conn.execute(
        sa.text("""
        CREATE TABLE wallet_shards (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            account_index INTEGER NOT NULL,
            next_address_index INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(
        sa.text("CREATE UNIQUE INDEX ix_wallet_shards_merchant_account ON wallet_shards (merchant_id, account_index)")
    )

    # api_keys
    conn.execute(
        sa.text("""
        CREATE TABLE api_keys (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            key_hash VARCHAR(255) NOT NULL,
            key_prefix VARCHAR(20) NOT NULL,
            label VARCHAR(255),
            environment VARCHAR(10) NOT NULL DEFAULT 'test',
            is_active BOOLEAN NOT NULL DEFAULT true,
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_api_keys_prefix ON api_keys (key_prefix)"))
    conn.execute(sa.text("CREATE INDEX ix_api_keys_merchant ON api_keys (merchant_id)"))

    # webhook_deliveries
    conn.execute(
        sa.text("""
        CREATE TABLE webhook_deliveries (
            id UUID PRIMARY KEY,
            merchant_id UUID NOT NULL REFERENCES merchants(id),
            invoice_id UUID REFERENCES invoices(id),
            event_type VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL,
            url VARCHAR(2048) NOT NULL,
            status webhook_status NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 7,
            last_attempt_at TIMESTAMPTZ,
            response_code INTEGER,
            response_body TEXT,
            next_retry_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_webhook_deliveries_merchant ON webhook_deliveries (merchant_id)"))
    conn.execute(sa.text("CREATE INDEX ix_webhook_deliveries_invoice_id ON webhook_deliveries (invoice_id)"))
    conn.execute(
        sa.text(
            "CREATE INDEX ix_webhook_deliveries_retry ON webhook_deliveries (next_retry_at)"
            " WHERE status = 'pending'::webhook_status"
        )
    )

    # audit_log
    conn.execute(
        sa.text("""
        CREATE TABLE audit_log (
            id UUID PRIMARY KEY,
            merchant_id UUID REFERENCES merchants(id),
            action VARCHAR(128) NOT NULL,
            entity_type VARCHAR(64),
            entity_id UUID,
            details JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    )
    conn.execute(sa.text("CREATE INDEX ix_audit_log_action ON audit_log (action)"))
    conn.execute(sa.text("CREATE INDEX ix_audit_log_merchant_created ON audit_log (merchant_id, created_at)"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in [
        "audit_log",
        "webhook_deliveries",
        "api_keys",
        "wallet_shards",
        "subscription_payments",
        "subscriptions",
        "customers",
        "payments",
        "invoice_addresses",
        "invoices",
        "merchants",
    ]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    for enum in ["webhook_status", "subscription_status", "payment_status", "invoice_status"]:
        conn.execute(sa.text(f"DROP TYPE IF EXISTS {enum}"))
