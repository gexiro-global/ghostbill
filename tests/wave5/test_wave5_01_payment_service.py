import pytest
from sqlalchemy import select

from app.db.models import AuditLog, InvoiceStatus, PaymentStatus, WebhookDelivery
from app.services.monero_rpc import DUST_THRESHOLD_ATOMIC
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import create_test_invoice, fake_tx_hash, payment_count, process_transfer_and_dispatch, webhook_events

pytestmark = pytest.mark.service


async def test_process_transfer_detected(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
    )
    await db_session.commit()
    await db_session.refresh(invoice)

    assert payment is not None
    assert payment.status == PaymentStatus.detected
    assert invoice.status == InvoiceStatus.pending


async def test_process_transfer_confirmed(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.paid
    assert invoice.paid_at is not None


async def test_partial_payment(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"], amount_atomic=1_000_000_000_000)
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=300_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=200_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.partially_paid


async def test_exact_payment(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.paid


async def test_overpayment(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic + 1,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.overpaid


async def test_dust_filter(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=DUST_THRESHOLD_ATOMIC - 1,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    assert payment is None
    assert await payment_count(db_session, invoice.id) == 0


async def test_process_transfer_creates_audit(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
        tx_hash=fake_tx_hash(),
    )
    await db_session.commit()

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.merchant_id == invoice.merchant_id, AuditLog.action == "payment.detected")
        )
    ).scalar_one_or_none()
    assert audit is not None


async def test_process_transfer_creates_webhook(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
    )
    await db_session.commit()

    assert "payment.detected" in await webhook_events(db_session, invoice.id)
    assert (await db_session.execute(select(WebhookDelivery).where(WebhookDelivery.invoice_id == invoice.id))).first()
