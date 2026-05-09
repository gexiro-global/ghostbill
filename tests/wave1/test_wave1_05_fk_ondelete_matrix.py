import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

DB_DSN = os.getenv("GHOSTBILL_TEST_DB", "postgresql://ghostbill:CHANGE_ME@127.0.0.1:5445/ghostbill")


def _as_str(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


EXPECTED = {
    ("invoice_addresses", "invoice_id", "invoices"): "c",
    ("audit_log", "merchant_id", "merchants"): "n",
    ("api_keys", "merchant_id", "merchants"): "r",
    ("customers", "merchant_id", "merchants"): "r",
    ("invoices", "merchant_id", "merchants"): "r",
    ("payments", "invoice_id", "invoices"): "r",
    ("subscription_payments", "subscription_id", "subscriptions"): "r",
    ("subscription_payments", "invoice_id", "invoices"): "r",
    ("subscription_renewal_events", "invoice_id", "invoices"): "r",
    ("subscriptions", "merchant_id", "merchants"): "r",
    ("subscriptions", "customer_id", "customers"): "r",
    ("subscriptions", "prepay_invoice_id", "invoices"): "r",
    ("wallet_shards", "merchant_id", "merchants"): "r",
    ("webhook_deliveries", "merchant_id", "merchants"): "r",
    ("webhook_deliveries", "invoice_id", "invoices"): "r",
    ("webhook_dead_letters", "merchant_id", "merchants"): "r",
    ("webhook_dead_letters", "delivery_id", "webhook_deliveries"): "r",
    ("subscription_renewal_events", "subscription_id", "subscriptions"): "c",
}


@pytest_asyncio.fixture
async def conn():
    c = await asyncpg.connect(dsn=DB_DSN)
    try:
        yield c
    finally:
        await c.close()


async def _fk_actions(conn):
    rows = await conn.fetch(
        """
        SELECT rel.relname AS table_name, att.attname AS column_name, refrel.relname AS ref_table, con.confdeltype
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_class refrel ON refrel.oid = con.confrelid
        JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, n) ON true
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
        WHERE con.contype = 'f'
        """
    )
    return {(r["table_name"], r["column_name"], r["ref_table"]): _as_str(r["confdeltype"]) for r in rows}


async def test_schema_05(conn):
    """Wave 1 / w1_05a: every FK has the correct ondelete policy per matrix."""
    actions = await _fk_actions(conn)
    for key, expected_action in EXPECTED.items():
        assert key in actions, f"FK missing: {key}"
        assert actions[key] == expected_action, f"FK {key} has {actions[key]!r}, expected {expected_action!r}"


async def test_behavior_05(conn):
    """DELETE invoice cascades to invoice_addresses (CASCADE policy)."""
    tx = conn.transaction()
    await tx.start()
    try:
        merchant_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        address_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO merchants (id, name, monero_address, environment, is_active) "
            "VALUES ($1, 'Wave1 Merchant', $2, 'test', true)",
            merchant_id,
            "4" + "1" * 94,
        )
        await conn.execute(
            """
            INSERT INTO invoices (id, merchant_id, amount_atomic, amount_xmr, status, expires_at)
            VALUES ($1, $2, 1000000000000, 1.0, 'pending'::invoice_status, NOW() + INTERVAL '1 hour')
            """,
            invoice_id,
            merchant_id,
        )
        await conn.execute(
            """
            INSERT INTO invoice_addresses (id, invoice_id, address, address_index, account_index)
            VALUES ($1, $2, $3, 17, 0)
            """,
            address_id,
            invoice_id,
            "8" + "2" * 94,
        )
        await conn.execute("DELETE FROM invoices WHERE id = $1", invoice_id)
        remaining = await conn.fetchval("SELECT COUNT(*) FROM invoice_addresses WHERE id = $1", address_id)
        assert remaining == 0
    finally:
        await tx.rollback()
