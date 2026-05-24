import pytest
from sqlalchemy import select

from app.db.models import Invoice, Merchant

from .conftest import cleanup_merchant, create_test_invoice, create_test_merchant

pytestmark = pytest.mark.service


async def test_independent_merchants(db_session):
    first = await create_test_merchant(db_session)
    second = await create_test_merchant(db_session)
    try:
        first_invoice = await create_test_invoice(db_session, first["merchant_id"])
        second_invoice = await create_test_invoice(db_session, second["merchant_id"])

        first_rows = (
            (await db_session.execute(select(Invoice).where(Invoice.merchant_id == first["merchant_id"])))
            .scalars()
            .all()
        )
        second_rows = (
            (await db_session.execute(select(Invoice).where(Invoice.merchant_id == second["merchant_id"])))
            .scalars()
            .all()
        )

        assert [row.id for row in first_rows] == [first_invoice.id]
        assert [row.id for row in second_rows] == [second_invoice.id]
    finally:
        await cleanup_merchant(db_session, first["merchant_id"])
        await cleanup_merchant(db_session, second["merchant_id"])


async def test_no_data_leaks(db_session):
    merchant = await create_test_merchant(db_session)
    merchant_id = merchant["merchant_id"]
    await create_test_invoice(db_session, merchant_id)
    await cleanup_merchant(db_session, merchant_id)

    assert (await db_session.execute(select(Merchant).where(Merchant.id == merchant_id))).scalar_one_or_none() is None
    assert (await db_session.execute(select(Invoice).where(Invoice.merchant_id == merchant_id))).scalars().all() == []
