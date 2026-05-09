import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

DB_DSN = os.getenv("GHOSTBILL_TEST_DB", "postgresql://ghostbill:CHANGE_ME@127.0.0.1:5445/ghostbill")


def _as_str(value):
    """Decode pg_constraint single-char fields (asyncpg returns bytes)."""
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


async def test_schema_01(conn):
    """Wave 1 / w1_01a: payments has UNIQUE (invoice_id, tx_hash)."""
    row = await conn.fetchrow(
        """
        SELECT con.contype, array_agg(att.attname ORDER BY ord.n) AS cols
        FROM pg_constraint con
        JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, n) ON true
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
        WHERE con.conname = 'uq_payments_invoice_tx'
        GROUP BY con.contype
        """
    )
    assert row is not None, "uq_payments_invoice_tx constraint missing"
    assert _as_str(row["contype"]) == "u"
    assert row["cols"] == ["invoice_id", "tx_hash"]


async def test_behavior_01(conn):
    """Inserting two payments with same (invoice_id, tx_hash) raises UniqueViolationError."""
    tx = conn.transaction()
    await tx.start()
    try:
        merchant_id = uuid.uuid4()
        invoice_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO merchants (id, name, monero_address, environment, is_active)
            VALUES ($1, 'Wave1 Merchant', $2, 'test', true)
            """,
            merchant_id,
            "4" + "a" * 94,
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
            INSERT INTO payments (id, invoice_id, tx_hash, amount_atomic, amount_xmr, status, confirmations)
            VALUES ($1, $2, $3, 1, 0.000000000001, 'detected'::payment_status, 0)
            """,
            uuid.uuid4(),
            invoice_id,
            "b" * 64,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO payments (id, invoice_id, tx_hash, amount_atomic, amount_xmr, status, confirmations)
                VALUES ($1, $2, $3, 2, 0.000000000002, 'detected'::payment_status, 0)
                """,
                uuid.uuid4(),
                invoice_id,
                "b" * 64,
            )
    finally:
        await tx.rollback()
