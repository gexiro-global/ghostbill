import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.models import InvoiceStatus, Payment
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import create_test_invoice, fake_tx_hash, process_transfer_and_dispatch

pytestmark = [pytest.mark.service, pytest.mark.slow]


async def _process_in_isolated_session(
    address_index: int,
    tx_hash: str,
    amount_atomic: int,
) -> None:
    """Run process_transfer in a completely isolated engine+session."""
    eng = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with fac() as session:
        try:
            await process_transfer_and_dispatch(
                session,
                account_index=0,
                address_index=address_index,
                tx_hash=tx_hash,
                amount_atomic=amount_atomic,
                confirmations=CONFIRMATION_THRESHOLD,
            )
            await session.commit()
        except Exception:
            await session.rollback()
    await eng.dispose()


async def test_concurrent_same_tx_hash(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    tx_hash = fake_tx_hash()
    addr_idx = invoice._test_addr_idx
    amount = invoice.amount_atomic

    await asyncio.gather(*[_process_in_isolated_session(addr_idx, tx_hash, amount) for _ in range(5)])

    rows = (
        (await db_session.execute(select(Payment).where(Payment.invoice_id == invoice.id, Payment.tx_hash == tx_hash)))
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_concurrent_two_partials(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"], amount_atomic=1_000_000_000_000)
    addr_idx = invoice._test_addr_idx

    await asyncio.gather(
        _process_in_isolated_session(addr_idx, fake_tx_hash(), 400_000_000_000),
        _process_in_isolated_session(addr_idx, fake_tx_hash(), 300_000_000_000),
    )
    await db_session.refresh(invoice)

    assert invoice.status == InvoiceStatus.partially_paid


async def test_payment_during_cancellation(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    addr_idx = invoice._test_addr_idx
    amount = invoice.amount_atomic

    async def cancel():
        from app.services.invoice_service import InvoiceStateError, invoice_service

        eng = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
        fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with fac() as session:
            try:
                await invoice_service.cancel_invoice(session, service_merchant["merchant_id"], invoice.id)
                await session.commit()
            except (InvoiceStateError, Exception):
                await session.rollback()
        await eng.dispose()

    await asyncio.gather(
        cancel(),
        _process_in_isolated_session(addr_idx, fake_tx_hash(), amount),
    )
    await db_session.refresh(invoice)

    # Both outcomes valid: paid (payment won) or cancelled (cancel won)
    assert invoice.status in (InvoiceStatus.cancelled, InvoiceStatus.paid)
