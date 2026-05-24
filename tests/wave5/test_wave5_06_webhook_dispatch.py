import json

import pytest
from sqlalchemy import select

from app.db.models import WebhookDeadLetter, WebhookDelivery, WebhookStatus
from app.services.payment_service import CONFIRMATION_THRESHOLD
from app.services.webhook_payloads import sign_payload, verify_signature
from app.services.webhook_service import webhook_service

from .conftest import create_test_invoice, process_transfer_and_dispatch

pytestmark = pytest.mark.service


async def test_invoice_paid_dispatches_webhook(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    events = (
        await db_session.execute(select(WebhookDelivery.event_type).where(WebhookDelivery.invoice_id == invoice.id))
    ).scalars()
    assert "invoice.paid" in list(events)


async def test_webhook_payload_structure(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    await db_session.commit()

    delivery = (
        await db_session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.invoice_id == invoice.id,
                WebhookDelivery.event_type == "invoice.paid",
            )
        )
    ).scalar_one()
    assert "event" in delivery.payload
    assert "timestamp" in delivery.payload
    assert "invoice" in delivery.payload
    inv = delivery.payload["invoice"]
    for key in ("amount_atomic", "amount_xmr", "status"):
        assert key in inv, f"Missing {key} in payload.invoice"


async def test_webhook_hmac_signature(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
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
    payload_bytes = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True).encode()
    signature = sign_payload(
        payload_bytes,
        service_merchant["webhook_secret"],
        timestamp="t",
        delivery_id=str(delivery.id),
    )
    assert verify_signature(
        payload_bytes,
        service_merchant["webhook_secret"],
        signature,
        timestamp="t",
        delivery_id=str(delivery.id),
    )


async def test_webhook_retry_on_failure(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    delivery = (
        (await db_session.execute(select(WebhookDelivery).where(WebhookDelivery.invoice_id == invoice.id)))
        .scalars()
        .first()
    )
    await webhook_service.process_delivery_result(db_session, delivery, success=False)
    await db_session.commit()

    assert delivery.status == WebhookStatus.pending
    assert delivery.attempts == 1
    assert delivery.next_retry_at is not None


async def test_webhook_dlq_after_exhaustion(db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    await process_transfer_and_dispatch(
        db_session,
        account_index=0,
        address_index=invoice._test_addr_idx,
        amount_atomic=invoice.amount_atomic,
        confirmations=CONFIRMATION_THRESHOLD,
    )
    delivery = (
        (await db_session.execute(select(WebhookDelivery).where(WebhookDelivery.invoice_id == invoice.id)))
        .scalars()
        .first()
    )
    delivery.attempts = delivery.max_attempts - 1
    await webhook_service.process_delivery_result(db_session, delivery, success=False)
    await db_session.commit()

    assert delivery.status == WebhookStatus.dead_lettered
    dlq = (
        await db_session.execute(select(WebhookDeadLetter).where(WebhookDeadLetter.delivery_id == delivery.id))
    ).scalar_one()
    assert dlq
