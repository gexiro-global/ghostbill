import pytest
from sqlalchemy import select

from app.db.models import InvoiceStatus, WebhookDelivery
from app.services.payment_service import CONFIRMATION_THRESHOLD

from .conftest import (
    auth_headers,
    cleanup_merchant,
    create_test_invoice,
    create_test_merchant,
    create_test_subscription,
    process_transfer_and_dispatch,
)

pytestmark = pytest.mark.integration


async def test_no_auth_rejected(client):
    for path in ("/v1/invoices", "/v1/customers"):
        resp = await client.get(path)
        assert resp.status_code == 401
    for path in ("/v1/invoices",):
        resp = await client.post(path, json={"amount_xmr": "1"})
        assert resp.status_code == 401


async def test_invalid_key_rejected(client):
    resp = await client.get("/v1/invoices", headers=auth_headers("gb_live_not_a_real_key"))
    assert resp.status_code == 401


async def test_cross_merchant_invoice(client, db_session, service_merchant):
    other = await create_test_merchant(db_session)
    invoice = await create_test_invoice(db_session, other["merchant_id"])
    try:
        resp = await client.get(f"/v1/invoices/{invoice.id}", headers=auth_headers(service_merchant["api_key"]))
        assert resp.status_code == 404
    finally:
        await cleanup_merchant(db_session, other["merchant_id"])


async def test_cross_merchant_subscription(client, db_session, service_merchant):
    other = await create_test_merchant(db_session)
    _, sub = await create_test_subscription(db_session, other["merchant_id"])
    try:
        resp = await client.get(f"/v1/subscriptions/{sub.id}", headers=auth_headers(service_merchant["api_key"]))
        assert resp.status_code == 404
    finally:
        await cleanup_merchant(db_session, other["merchant_id"])


async def test_cross_merchant_customer(client, db_session, service_merchant):
    other = await create_test_merchant(db_session)
    customer, _ = await create_test_subscription(db_session, other["merchant_id"])
    try:
        resp = await client.get(f"/v1/customers/{customer.id}", headers=auth_headers(service_merchant["api_key"]))
        assert resp.status_code == 404
    finally:
        await cleanup_merchant(db_session, other["merchant_id"])


async def test_cross_merchant_webhook_retry(client, db_session, service_merchant):
    other = await create_test_merchant(db_session)
    invoice = await create_test_invoice(db_session, other["merchant_id"], status=InvoiceStatus.pending)
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    delivery = (
        (await db_session.execute(select(WebhookDelivery).where(WebhookDelivery.invoice_id == invoice.id)))
        .scalars()
        .first()
    )
    try:
        resp = await client.post(f"/v1/webhooks/{delivery.id}/retry", headers=auth_headers(service_merchant["api_key"]))
        assert resp.status_code in (403, 404)
    finally:
        await cleanup_merchant(db_session, other["merchant_id"])


async def test_cross_merchant_payment(client, db_session, service_merchant):
    other = await create_test_merchant(db_session)
    invoice = await create_test_invoice(db_session, other["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()
    try:
        resp = await client.get(
            f"/v1/payments?invoice_id={invoice.id}",
            headers=auth_headers(service_merchant["api_key"]),
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []
    finally:
        await cleanup_merchant(db_session, other["merchant_id"])
