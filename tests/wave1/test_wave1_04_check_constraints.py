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
    "ck_payments_amount_atomic_nonnegative",
    "ck_payments_confirmations_nonnegative",
    "ck_invoices_amount_atomic_positive",
    "ck_subscriptions_amount_atomic_positive",
    "ck_subscriptions_interval_days_positive",
    "ck_subscriptions_grace_days_soft_nonnegative",
    "ck_subscriptions_grace_days_hard_nonnegative",
    "ck_subscriptions_grace_days_order",
    "ck_subscriptions_trial_days_positive",
    "ck_subscription_payments_period_order",
    "ck_webhook_deliveries_attempts_nonnegative",
    "ck_webhook_dead_letters_retry_count_nonnegative",
}


@pytest_asyncio.fixture
async def conn():
    c = await asyncpg.connect(dsn=DB_DSN)
    try:
        yield c
    finally:
        await c.close()


async def test_schema_04(conn):
    """Wave 1 / w1_04a: all 12 CHECK constraints exist and are validated."""
    rows = await conn.fetch(
        "SELECT conname, contype, convalidated FROM pg_constraint WHERE conname = ANY($1::text[])",
        list(EXPECTED),
    )
    found = {r["conname"]: r for r in rows}
    assert set(found) == EXPECTED, f"missing CHECK constraints: {EXPECTED - set(found)}"
    for r in found.values():
        assert _as_str(r["contype"]) == "c"
        assert r["convalidated"] is True, f"{r['conname']} not validated"


async def test_behavior_04(conn):
    """CHECK constraint on invoices.amount_atomic > 0 blocks zero-amount inserts."""
    tx = conn.transaction()
    await tx.start()
    try:
        merchant_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO merchants (id, name, monero_address, environment, is_active) "
            "VALUES ($1, 'Wave1 Merchant', $2, 'test', true)",
            merchant_id,
            "4" + "f" * 94,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO invoices (id, merchant_id, amount_atomic, amount_xmr, status, expires_at)
                VALUES ($1, $2, 0, 0, 'pending'::invoice_status, NOW() + INTERVAL '1 hour')
                """,
                uuid.uuid4(),
                merchant_id,
            )
    finally:
        await tx.rollback()
