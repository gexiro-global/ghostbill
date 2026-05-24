import pytest
from sqlalchemy import select

from app.db.models import AuditLog, Payment, PaymentStatus
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import create_test_invoice, fake_tx_hash, process_transfer_and_dispatch, webhook_events

pytestmark = pytest.mark.service


async def test_confirmation_monotonic(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=5,
    )
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=3,
    )
    await db_session.commit()

    payment = (await db_session.execute(select(Payment).where(Payment.tx_hash == tx_hash))).scalar_one()
    assert payment.confirmations == 5


async def test_confirmed_at_set_on_threshold(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    payment = await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    await db_session.refresh(payment)

    assert payment.status == PaymentStatus.confirmed
    assert payment.confirmed_at is not None


async def test_block_height_updated(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
        block_height=None,
    )
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
        block_height=321,
    )
    await db_session.commit()

    payment = (await db_session.execute(select(Payment).where(Payment.tx_hash == tx_hash))).scalar_one()
    assert payment.block_height == 321


async def test_confirmation_audit_row(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
    )
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "payment.confirmed"))).scalar_one()
    assert audit.details["tx_hash"] == tx_hash


async def test_confirmation_webhook(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=0,
    )
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    assert "payment.confirmed" in await webhook_events(db_session, invoice.id)
