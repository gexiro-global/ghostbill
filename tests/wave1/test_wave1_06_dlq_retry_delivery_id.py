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


@pytest_asyncio.fixture
async def conn():
    c = await asyncpg.connect(dsn=DB_DSN)
    try:
        yield c
    finally:
        await c.close()


async def test_schema_06(conn):
    """Wave 1 / w1_06a: webhook_dead_letters.retry_delivery_id column + FK with ON DELETE SET NULL."""
    row = await conn.fetchrow(
        """
        SELECT con.confdeltype, idx.indexdef
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, n) ON true
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
        JOIN pg_indexes idx ON idx.indexname = 'ix_webhook_dead_letters_retry_delivery'
        WHERE rel.relname = 'webhook_dead_letters'
          AND att.attname = 'retry_delivery_id'
          AND con.contype = 'f'
        """
    )
    assert row is not None
    assert _as_str(row["confdeltype"]) == "n"
    assert "(retry_delivery_id)" in row["indexdef"]


async def test_behavior_06(conn):
    """DELETE retry webhook_delivery sets retry_delivery_id to NULL on linked dead-letter row."""
    tx = conn.transaction()
    await tx.start()
    try:
        merchant_id = uuid.uuid4()
        original_delivery_id = uuid.uuid4()
        retry_delivery_id = uuid.uuid4()
        dead_letter_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO merchants (id, name, monero_address, environment, is_active) "
            "VALUES ($1, 'Wave1 Merchant', $2, 'test', true)",
            merchant_id,
            "4" + "3" * 94,
        )
        for delivery_id in (original_delivery_id, retry_delivery_id):
            await conn.execute(
                """
                INSERT INTO webhook_deliveries (
                    id, merchant_id, event_type, payload, url, status, attempts, max_attempts
                )
                VALUES (
                    $1, $2, 'invoice.created', '{}'::jsonb,
                    'https://example.invalid/webhook', 'pending'::webhook_status, 0, 7
                )
                """,
                delivery_id,
                merchant_id,
            )
        await conn.execute(
            """
            INSERT INTO webhook_dead_letters (
                id, delivery_id, merchant_id, event_type, payload,
                original_created_at, retry_count, resolved, retry_delivery_id
            )
            VALUES ($1, $2, $3, 'invoice.created', '{}'::jsonb, NOW(), 0, false, $4)
            """,
            dead_letter_id,
            original_delivery_id,
            merchant_id,
            retry_delivery_id,
        )
        await conn.execute("DELETE FROM webhook_deliveries WHERE id = $1", retry_delivery_id)
        value = await conn.fetchval("SELECT retry_delivery_id FROM webhook_dead_letters WHERE id = $1", dead_letter_id)
        assert value is None
    finally:
        await tx.rollback()
