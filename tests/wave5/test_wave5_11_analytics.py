from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.db.models import Payment
from app.services.analytics_service import get_revenue
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import (
    create_test_invoice,
    create_test_merchant,
    fake_tx_hash,
    handle_reorg_and_dispatch,
    process_transfer_and_dispatch,
)

pytestmark = pytest.mark.service


class FakeRedis:
    async def get(self, key):
        return None

    async def set(self, key, value, ex=None):
        return True


async def test_revenue_counts_confirmed_only(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
    )
    await db_session.commit()

    revenue = await get_revenue(db_session, FakeRedis(), service_merchant["merchant_id"], "30d")
    assert revenue["gross_received_atomic"] == 0


async def test_revenue_merchant_isolated(db_session, service_merchant):
    other = await create_test_merchant(db_session)
    try:
        invoice = await create_test_invoice(db_session, other["merchant_id"], amount_atomic=500_000_000_000)
        await process_transfer_and_dispatch(
            db_session,
            account_index=0,
            address_index=invoice._test_addr_idx,
            amount_atomic=500_000_000_000,
            confirmations=CONFIRMATION_THRESHOLD,
        )
        await db_session.commit()
        revenue = await get_revenue(db_session, FakeRedis(), service_merchant["merchant_id"], "30d")
        assert revenue["gross_received_atomic"] == 0
    finally:
        from .conftest import cleanup_merchant

        await cleanup_merchant(db_session, other["merchant_id"])


async def test_revenue_date_filter(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"], amount_atomic=800_000_000_000)
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=800_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.execute(
        update(Payment)
        .where(Payment.id == payment.id)
        .values(confirmed_at=datetime.now(timezone.utc) - timedelta(days=400))
    )
    await db_session.commit()

    revenue = await get_revenue(db_session, FakeRedis(), service_merchant["merchant_id"], "30d")
    assert revenue["gross_received_atomic"] == 0


async def test_analytics_excludes_orphaned(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"], amount_atomic=900_000_000_000)
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=900_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await handle_reorg_and_dispatch(db_session, payment)
    await db_session.commit()

    revenue = await get_revenue(db_session, FakeRedis(), service_merchant["merchant_id"], "30d")
    assert revenue["gross_received_atomic"] == 0


async def test_analytics_overpayment_included(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"], amount_atomic=1_000_000_000_000)
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=fake_tx_hash(),
        amount_atomic=1_200_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    revenue = await get_revenue(db_session, FakeRedis(), service_merchant["merchant_id"], "30d")
    assert revenue["gross_received_atomic"] == 1_200_000_000_000
    assert revenue["invoice_revenue_atomic"] == 1_000_000_000_000
