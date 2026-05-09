import os

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

DB_DSN = os.getenv("GHOSTBILL_TEST_DB", "postgresql://ghostbill:CHANGE_ME@127.0.0.1:5445/ghostbill")

EXPECTED = {
    "ix_subscriptions_customer_id": ("subscriptions", "customer_id"),
    "ix_subscriptions_prepay_invoice_id": ("subscriptions", "prepay_invoice_id"),
    "ix_webhook_deliveries_invoice_id": ("webhook_deliveries", "invoice_id"),
    "ix_subscription_payments_invoice_id": ("subscription_payments", "invoice_id"),
    "ix_webhook_dead_letters_delivery_id": ("webhook_dead_letters", "delivery_id"),
    "ix_subscription_renewal_events_invoice_id": ("subscription_renewal_events", "invoice_id"),
}


@pytest_asyncio.fixture
async def conn():
    c = await asyncpg.connect(dsn=DB_DSN)
    try:
        yield c
    finally:
        await c.close()


async def test_schema_03(conn):
    """Wave 1 / w1_03a: 6 missing FK indexes exist on correct tables."""
    rows = await conn.fetch(
        "SELECT indexname, tablename, indexdef FROM pg_indexes WHERE indexname = ANY($1::text[])",
        list(EXPECTED),
    )
    found = {r["indexname"]: r for r in rows}
    assert set(found) == set(EXPECTED), f"missing indexes: {set(EXPECTED) - set(found)}"
    for name, (table, column) in EXPECTED.items():
        assert found[name]["tablename"] == table
        assert f"({column})" in found[name]["indexdef"]


async def test_behavior_03(conn):
    """Each FK index targets the correct (table, column) and is non-unique, valid."""
    for index_name, (expected_table, expected_column) in EXPECTED.items():
        row = await conn.fetchrow(
            """
            SELECT
                cls.relname AS table_name,
                array_agg(att.attname ORDER BY ord.n) AS cols,
                ix.indisunique AS is_unique,
                ix.indisvalid AS is_valid
            FROM pg_index ix
            JOIN pg_class idx ON idx.oid = ix.indexrelid
            JOIN pg_class cls ON cls.oid = ix.indrelid
            JOIN unnest(ix.indkey) WITH ORDINALITY AS ord(attnum, n) ON true
            JOIN pg_attribute att ON att.attrelid = ix.indrelid AND att.attnum = ord.attnum
            WHERE idx.relname = $1
            GROUP BY cls.relname, ix.indisunique, ix.indisvalid
            """,
            index_name,
        )
        assert row is not None, f"index {index_name} not found in pg_index"
        assert row["table_name"] == expected_table, f"{index_name} on wrong table"
        assert row["cols"] == [expected_column], f"{index_name} on wrong column(s)"
        assert row["is_unique"] is False, f"{index_name} should be non-unique FK index"
        assert row["is_valid"] is True, f"{index_name} must be valid"
