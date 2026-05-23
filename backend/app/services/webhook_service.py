"""Webhook dispatch service — queue, delivery, retry, DLQ.

Payload builders, HMAC signing, constants in webhook_payloads.py.
Phase 6B: Dead Letter Queue — failed deliveries moved to DLQ after max retries.
"""

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tor_proxy import tor_proxy
from app.db.models import (
    Invoice,
    Merchant,
    Payment,
    Subscription,
    WebhookDeadLetter,
    WebhookDelivery,
    WebhookStatus,
)
from app.services.webhook_payloads import (
    DELIVERY_TIMEOUT,
    JITTER_MAX,
    JITTER_MIN,
    MAX_ATTEMPTS,
    VALID_EVENTS,
    build_invoice_payload,
    build_payment_payload,
    build_subscription_payload,
    calculate_next_retry,
    sign_payload,
)

logger = logging.getLogger(__name__)


class WebhookRetryNotFoundError(Exception):
    """Delivery retry target does not exist for the merchant."""


class WebhookRetryConflictError(Exception):
    """Delivery retry target is already completed or resolved."""


class WebhookRetryInvalidStateError(Exception):
    """Delivery retry target exists but is not retryable."""


class WebhookService:
    """Webhook dispatch — stateless, operates on provided DB session."""

    async def queue_webhook(
        self,
        db: AsyncSession,
        merchant: Merchant,
        event_type: str,
        payload: dict[str, Any],
        invoice_id: uuid.UUID | None = None,
    ) -> WebhookDelivery | None:
        """Create webhook delivery record. Returns None if no URL configured."""
        if event_type not in VALID_EVENTS:
            raise ValueError(f"Unknown webhook event type: {event_type}")
        if not merchant.webhook_url or not merchant.webhook_secret:
            return None
        url_valid, url_error = tor_proxy.validate_webhook_url(merchant.webhook_url)
        if not url_valid:
            logger.warning("Webhook URL rejected for %s: %s", merchant.id, url_error)
            return None

        delivery = WebhookDelivery(
            merchant_id=merchant.id,
            invoice_id=invoice_id,
            event_type=event_type,
            payload=payload,
            url=merchant.webhook_url,
            status=WebhookStatus.pending,
            attempts=0,
            max_attempts=MAX_ATTEMPTS,
            next_retry_at=datetime.now(timezone.utc),
        )
        db.add(delivery)
        await db.flush()
        logger.info("Webhook queued: %s, event=%s", delivery.id, event_type)
        return delivery

    async def dispatch_events(
        self,
        db: AsyncSession,
        events: list[str],
        merchant: Merchant,
        invoice: Invoice,
        payment: Payment | None = None,
    ) -> list[WebhookDelivery]:
        """Queue webhook deliveries for payment/invoice events."""
        deliveries = []
        for event_type in events:
            if event_type.startswith("payment.") and payment is not None:
                payload = build_payment_payload(payment, invoice)
            else:
                payload = build_invoice_payload(invoice)
            payload["event"] = event_type
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            d = await self.queue_webhook(db, merchant, event_type, payload, invoice.id)
            if d:
                deliveries.append(d)
        return deliveries

    async def dispatch_subscription_event(
        self,
        db: AsyncSession,
        event_type: str,
        subscription: Subscription,
        invoice_id: uuid.UUID | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        reason: str | None = None,
    ) -> WebhookDelivery | None:
        """Queue a single subscription webhook event."""
        merchant = (
            await db.execute(select(Merchant).where(Merchant.id == subscription.merchant_id))
        ).scalar_one_or_none()
        if merchant is None:
            return None
        payload = build_subscription_payload(event_type, subscription, invoice_id, period_start, period_end, reason)
        payload["event"] = event_type
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return await self.queue_webhook(db, merchant, event_type, payload)

    async def attempt_delivery(self, delivery: WebhookDelivery, webhook_secret: str) -> bool:
        """Attempt to deliver a single webhook via HTTP POST."""
        await asyncio.sleep(random.uniform(JITTER_MIN, JITTER_MAX))
        payload_bytes = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = datetime.now(timezone.utc).isoformat()
        delivery_id = str(delivery.id)
        signature = sign_payload(payload_bytes, webhook_secret, timestamp=timestamp, delivery_id=delivery_id)
        headers = {
            "Content-Type": "application/json",
            "X-GhostBill-Signature": signature,
            "X-GhostBill-Signature-Version": "v2",
            "X-GhostBill-Timestamp": timestamp,
            "X-GhostBill-Delivery-Id": delivery_id,
            "X-GhostBill-Event-ID": delivery_id,
            "X-GhostBill-Event-Type": delivery.event_type,
            "User-Agent": "GhostBill-Webhook/1.0",
        }
        try:
            response = await tor_proxy.post(
                url=delivery.url,
                content=payload_bytes,
                headers=headers,
                timeout=DELIVERY_TIMEOUT,
            )
            delivery.response_code = response.status_code
            delivery.response_body = response.text[:2048] if response.text else None
            success = 200 <= response.status_code < 300
            if not success:
                logger.warning("Webhook failed: %s, status=%d", delivery.id, response.status_code)
            return success
        except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
            delivery.response_code = None
            delivery.response_body = str(exc)[:2048]
            logger.warning("Webhook error: %s, %s", delivery.id, exc)
            return False

    async def get_pending_deliveries(self, db: AsyncSession, limit: int = 50) -> list[WebhookDelivery]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.status == WebhookStatus.pending, WebhookDelivery.next_retry_at <= now)
            .order_by(WebhookDelivery.next_retry_at.asc())
            .limit(limit)
        )
        return list((await db.execute(stmt)).scalars().all())

    async def claim_pending_deliveries(self, db: AsyncSession, limit: int = 50) -> list[WebhookDelivery]:
        """Claim pending deliveries with row locks.

        WebhookStatus has no in_progress value in the v1.3 schema. The claim is
        therefore the PostgreSQL row lock itself: concurrent workers using
        SKIP LOCKED will not see rows held by this transaction.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.status == WebhookStatus.pending, WebhookDelivery.next_retry_at <= now)
            .order_by(WebhookDelivery.next_retry_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        deliveries = list((await db.execute(stmt)).scalars().all())
        for delivery in deliveries:
            delivery.last_attempt_at = now
        await db.flush()
        return deliveries

    async def process_delivery_result(self, db: AsyncSession, delivery: WebhookDelivery, success: bool) -> None:
        """Process delivery result. On max retries → DLQ instead of just failed."""
        delivery.attempts += 1
        delivery.last_attempt_at = datetime.now(timezone.utc)
        if success:
            delivery.status = WebhookStatus.delivered
            delivery.next_retry_at = None
        elif delivery.attempts >= delivery.max_attempts:
            # Phase 6B: DLQ instead of just 'failed'
            await self._move_to_dlq(db, delivery)
        else:
            delivery.next_retry_at = calculate_next_retry(delivery.attempts)
        await db.flush()

    async def _move_to_dlq(
        self, db: AsyncSession, delivery: WebhookDelivery, failure_reason: str | None = None
    ) -> None:
        """Move failed delivery to Dead Letter Queue."""
        delivery.status = WebhookStatus.dead_lettered
        delivery.next_retry_at = None

        payload = dict(delivery.payload)
        payload["_dlq_details"] = {
            "attempt_count": delivery.attempts,
            "max_attempts": delivery.max_attempts,
            **({"failure_reason": failure_reason} if failure_reason else {}),
        }

        dlq_entry = WebhookDeadLetter(
            delivery_id=delivery.id,
            merchant_id=delivery.merchant_id,
            event_type=delivery.event_type,
            payload=payload,
            original_created_at=delivery.created_at,
            last_error=failure_reason or delivery.response_body or "Max retries exceeded",
        )
        db.add(dlq_entry)
        logger.warning(
            "Webhook dead-lettered: %s, event=%s, merchant=%s",
            delivery.id,
            delivery.event_type,
            delivery.merchant_id,
        )

    async def retry_delivery(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery:
        """Retry a failed or dead_lettered delivery."""
        delivery = (
            await db.execute(
                select(WebhookDelivery).where(
                    WebhookDelivery.id == delivery_id, WebhookDelivery.merchant_id == merchant_id
                )
            )
        ).scalar_one_or_none()
        if delivery is None:
            raise WebhookRetryNotFoundError
        if delivery.status == WebhookStatus.delivered:
            raise WebhookRetryConflictError
        if delivery.status not in (WebhookStatus.failed, WebhookStatus.dead_lettered):
            raise WebhookRetryInvalidStateError
        delivery.status = WebhookStatus.pending
        delivery.attempts = 0
        delivery.next_retry_at = datetime.now(timezone.utc)
        await db.flush()
        return delivery

    async def retry_dead_letter(
        self,
        db: AsyncSession,
        merchant: Merchant,
        dlq_entry: WebhookDeadLetter,
    ) -> WebhookDelivery:
        if dlq_entry.resolved:
            raise WebhookRetryConflictError
        new_delivery = await self.queue_webhook(
            db=db,
            merchant=merchant,
            event_type=dlq_entry.event_type,
            payload=dlq_entry.payload,
        )
        if new_delivery is None:
            raise WebhookRetryInvalidStateError
        dlq_entry.retry_count += 1
        dlq_entry.retry_delivery_id = new_delivery.id
        dlq_entry.last_retry_at = datetime.now(timezone.utc)
        return new_delivery

    async def mark_dlq_resolved_for_delivery(self, db: AsyncSession, delivery: WebhookDelivery) -> None:
        entry = (
            await db.execute(
                select(WebhookDeadLetter).where(
                    WebhookDeadLetter.retry_delivery_id == delivery.id,
                    WebhookDeadLetter.merchant_id == delivery.merchant_id,
                    WebhookDeadLetter.resolved.is_(False),
                )
            )
        ).scalar_one_or_none()
        if entry is None:
            return
        entry.resolved = True
        entry.resolved_at = datetime.now(timezone.utc)
        payload = dict(entry.payload)
        details = dict(payload.get("_dlq_details") or {})
        details["resolved_delivery_id"] = str(delivery.id)
        payload["_dlq_details"] = details
        entry.payload = payload
        await db.flush()


webhook_service = WebhookService()
