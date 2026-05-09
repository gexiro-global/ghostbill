import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

DB_DSN = os.getenv("GHOSTBILL_TEST_DB", "postgresql://ghostbill:CHANGE_ME@127.0.0.1:5445/ghostbill")


@pytest_asyncio.fixture
async def conn():
    c = await asyncpg.connect(dsn=DB_DSN)
    try:
        yield c
    finally:
        await c.close()


async def test_schema_02(conn):
    """Wave 1 / w1_02a: invoice_addresses unique (account_index, address_index)."""
    row = await conn.fetchrow(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE indexname = 'ix_invoice_addresses_index'
        """
    )
    assert row is not None
    assert "UNIQUE" in row["indexdef"].upper()
    assert "(account_index, address_index)" in row["indexdef"]


async def test_behavior_02(conn):
    """Inserting two invoice_addresses with same (account_index, address_index) raises UniqueViolationError."""
    tx = conn.transaction()
    await tx.start()
    try:
        merchant_id = uuid.uuid4()
        invoice_id_a = uuid.uuid4()
        invoice_id_b = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO merchants (id, name, monero_address, environment, is_active)
            VALUES ($1, 'Wave1 Merchant', $2, 'test', true)
            """,
            merchant_id,
            "4" + "c" * 94,
        )
        for inv in (invoice_id_a, invoice_id_b):
            await conn.execute(
                """
                INSERT INTO invoices (id, merchant_id, amount_atomic, amount_xmr, status, expires_at)
                VALUES ($1, $2, 1000000000000, 1.0, 'pending'::invoice_status, NOW() + INTERVAL '1 hour')
                """,
                inv,
                merchant_id,
            )
        await conn.execute(
            """
            INSERT INTO invoice_addresses (id, invoice_id, address, address_index, account_index)
            VALUES ($1, $2, $3, 9999, 0)
            """,
            uuid.uuid4(),
            invoice_id_a,
            "8" + "d" * 94,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO invoice_addresses (id, invoice_id, address, address_index, account_index)
                VALUES ($1, $2, $3, 9999, 0)
                """,
                uuid.uuid4(),
                invoice_id_b,
                "8" + "e" * 94,
            )
    finally:
        await tx.rollback()
