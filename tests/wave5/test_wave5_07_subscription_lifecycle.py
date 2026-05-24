from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models import InvoiceStatus, SubscriptionPayment, SubscriptionRenewalEvent, SubscriptionStatus
from app.services.subscription_grace import check_grace_periods, handle_subscription_payment
from app.services.subscription_prepay import handle_prepay_payment

from .conftest import (
    attach_subscription_payment,
    create_test_invoice,
    create_test_subscription,
    set_invoice_status,
)

pytestmark = pytest.mark.service


async def test_grace_period_active(db_session, service_merchant):
    _, sub = await create_test_subscription(db_session, service_merchant["merchant_id"])
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await attach_subscription_payment(
        db_session,
        sub,
        invoice,
        period_start=datetime.now(timezone.utc) - timedelta(days=1),
    )

    counts = await check_grace_periods(db_session)
    await db_session.commit()
    await db_session.refresh(sub)

    assert counts == {"soft": 0, "hard": 0, "recovered": 0}
    assert sub.status == SubscriptionStatus.active


async def test_grace_period_expired(db_session, service_merchant):
    _, sub = await create_test_subscription(
        db_session,
        service_merchant["merchant_id"],
        status=SubscriptionStatus.past_due,
    )
    invoice = await create_test_invoice(
        db_session,
        service_merchant["merchant_id"],
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    await attach_subscription_payment(
        db_session,
        sub,
        invoice,
        period_start=datetime.now(timezone.utc) - timedelta(days=10),
    )

    counts = await check_grace_periods(db_session)
    await db_session.commit()
    await db_session.refresh(sub)

    assert counts["hard"] == 1
    assert sub.status == SubscriptionStatus.expired


async def test_prepay_fulfillment_creates_periods(db_session, service_merchant):
    _, sub = await create_test_subscription(db_session, service_merchant["merchant_id"])
    invoice = await create_test_invoice(
        db_session,
        service_merchant["merchant_id"],
        metadata={"prepay": True, "subscription_id": str(sub.id), "periods": 3, "discount_pct": 0},
    )
    await set_invoice_status(db_session, invoice.id, InvoiceStatus.paid)
    await db_session.refresh(invoice)
    await handle_prepay_payment(db_session, invoice, sub)
    await db_session.commit()

    count = (
        (await db_session.execute(select(SubscriptionPayment).where(SubscriptionPayment.subscription_id == sub.id)))
        .scalars()
        .all()
    )
    assert len(count) == 3


async def test_prepay_fulfillment_idempotent(db_session, service_merchant):
    _, sub = await create_test_subscription(db_session, service_merchant["merchant_id"])
    invoice = await create_test_invoice(
        db_session,
        service_merchant["merchant_id"],
        metadata={"prepay": True, "subscription_id": str(sub.id), "periods": 2, "discount_pct": 0},
    )
    await set_invoice_status(db_session, invoice.id, InvoiceStatus.paid)
    await db_session.refresh(invoice)

    await handle_prepay_payment(db_session, invoice, sub)
    await handle_prepay_payment(db_session, invoice, sub)
    await db_session.commit()

    count = (
        (await db_session.execute(select(SubscriptionPayment).where(SubscriptionPayment.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    assert len(count) == 2


async def test_subscription_recovery_on_late_payment(db_session, service_merchant):
    _, sub = await create_test_subscription(
        db_session,
        service_merchant["merchant_id"],
        status=SubscriptionStatus.past_due,
    )
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await attach_subscription_payment(db_session, sub, invoice)
    await set_invoice_status(db_session, invoice.id, InvoiceStatus.late_paid)

    await handle_subscription_payment(db_session, invoice.id)
    await db_session.commit()
    await db_session.refresh(sub)

    events = (
        (
            await db_session.execute(
                select(SubscriptionRenewalEvent).where(SubscriptionRenewalEvent.subscription_id == sub.id)
            )
        )
        .scalars()
        .all()
    )
    assert sub.status == SubscriptionStatus.active
    assert events == []
