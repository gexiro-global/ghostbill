import pytest
from sqlalchemy import select

from app.db.models import AuditLog, InvoiceStatus, Payment, PaymentStatus
from app.services.invoice_service import invoice_service
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import create_test_invoice, handle_reorg_and_dispatch, process_transfer_and_dispatch, webhook_events

pytestmark = pytest.mark.service


async def _paid_invoice_with_payment(db_session, merchant_id, amount_atomic=1_000_000_000_000):
    invoice = await create_test_invoice(db_session, merchant_id, amount_atomic=amount_atomic)
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    return invoice, payment


async def test_reorg_reverts_paid_invoice(db_session, service_merchant):
    invoice, payment = await _paid_invoice_with_payment(db_session, service_merchant["merchant_id"])
    await handle_reorg_and_dispatch(db_session, payment)
    await db_session.commit()
    await db_session.refresh(invoice)
    await db_session.refresh(payment)

    assert payment.status == PaymentStatus.orphaned
    assert invoice.status == InvoiceStatus.pending


async def test_reorg_reverts_overpaid_invoice(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic + 123,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await handle_reorg_and_dispatch(db_session, payment)
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.pending


async def test_reorg_partial_still_partial(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"], amount_atomic=1_000_000_000_000)
    orphaned = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=400_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    survivor = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=300_000_000_000,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    await handle_reorg_and_dispatch(db_session, orphaned)
    await db_session.commit()
    await db_session.refresh(invoice)
    await db_session.refresh(survivor)

    assert invoice.status == InvoiceStatus.partially_paid
    assert survivor.status == PaymentStatus.confirmed


async def test_reorg_creates_audit_and_webhook(db_session, service_merchant):
    invoice, payment = await _paid_invoice_with_payment(db_session, service_merchant["merchant_id"])
    await handle_reorg_and_dispatch(db_session, payment)
    await db_session.commit()

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.merchant_id == invoice.merchant_id, AuditLog.action == "payment.orphaned")
        )
    ).scalar_one_or_none()
    assert audit is not None
    assert "payment.orphaned" in await webhook_events(db_session, invoice.id)
    assert "invoice.reverted" in await webhook_events(db_session, invoice.id)


async def test_reorg_cancelled_invoice_stays_cancelled(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await invoice_service.cancel_invoice(db_session, service_merchant["merchant_id"], invoice.id)
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await handle_reorg_and_dispatch(db_session, payment)
    await db_session.commit()
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.cancelled
    orphaned_payment = (await db_session.execute(select(Payment).where(Payment.invoice_id == invoice.id))).scalar_one()
    assert orphaned_payment.status == PaymentStatus.orphaned
