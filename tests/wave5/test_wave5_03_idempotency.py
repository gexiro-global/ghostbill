import pytest
from sqlalchemy import select

from app.db.models import Payment, PaymentStatus
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import create_test_invoice, fake_tx_hash, payment_count, process_transfer_and_dispatch

pytestmark = pytest.mark.service


async def test_duplicate_tx_hash_no_double_credit(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()

    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
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

    assert await payment_count(db_session, invoice.id) == 1


async def test_duplicate_tx_hash_updates_confirmations(db_session, service_merchant):
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

    payment = (await db_session.execute(select(Payment).where(Payment.tx_hash == tx_hash))).scalar_one()
    assert payment.status == PaymentStatus.confirmed
    assert payment.confirmations == CONFIRMATION_THRESHOLD


async def test_duplicate_tx_hash_different_amount(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        tx_hash=tx_hash,
        amount_atomic=invoice.amount_atomic // 2,
        confirmations=CONFIRMATION_THRESHOLD,
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

    payment = (await db_session.execute(select(Payment).where(Payment.tx_hash == tx_hash))).scalar_one()
    assert payment.amount_atomic == invoice.amount_atomic // 2
    assert await payment_count(db_session, invoice.id) == 1
