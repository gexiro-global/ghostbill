"""
Webhook dispatch service — HMAC-SHA256 signing, queue, delivery.

Responsibilities:
    - Create webhook delivery records in DB
    - Sign payloads with HMAC-SHA256 (merchant webhook_secret)
    - Deliver webhooks via HTTP POST with proper headers
    - Calculate retry schedule (7 attempts)
    - Random jitter 50-200ms (metadata protection)
    - Route outgoing via Tor SOCKS5 proxy (if enabled)

Headers sent:
    - Content-Type: application/json
    - X-GhostBill-Signature: HMAC-SHA256 hex digest
    - X-GhostBill-Event-ID: unique delivery UUID
    - X-GhostBill-Event-Type: event type string

Retry schedule (7 attempts):
    immediate → 1m → 5m → 30m → 2h → 12h → 24h → stop

Events (13 total):
    payment.detected, payment.confirmed, payment.orphaned
    invoice.paid, invoice.expired, invoice.partially_paid, invoice.overpaid, invoice.late_paid
    subscription.created, subscription.renewed, subscription.past_due,
    subscription.cancelled, subscription.payment_confirmed
"""

import asyncio
import hashlib
import hmac
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tor_proxy import tor_proxy
from app.db.models import (
    Invoice,
    Merchant,
    Payment,
    Subscription,
    WebhookDelivery,
    WebhookStatus,
)

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

MAX_ATTEMPTS: int = 7
DELIVERY_TIMEOUT: float = 10.0  # seconds per attempt

# Retry delays in seconds: 1m, 5m, 30m, 2h, 12h, 24h
RETRY_DELAYS: list[int] = [60, 300, 1800, 7200, 43200, 86400]

# Jitter range in seconds (metadata protection)
JITTER_MIN: float = 0.05
JITTER_MAX: float = 0.2

# Valid event types (13 total)
VALID_EVENTS: list[str] = [
    # Payment events (3)
    "payment.detected",
    "payment.confirmed",
    "payment.orphaned",
    # Invoice events (5)
    "invoice.paid",
    "invoice.expired",
    "invoice.partially_paid",
    "invoice.overpaid",
    "invoice.late_paid",
    # Subscription events (5) — Phase 5A
    "subscription.created",
    "subscription.renewed",
    "subscription.past_due",
    "subscription.cancelled",
    "subscription.payment_confirmed",
]


# ─── HMAC Signing ────────────────────────────────────────────────────────────

def sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Create HMAC-SHA256 signature for webhook payload.

    Args:
        payload_bytes: Raw JSON bytes of the payload.
        secret: Merchant webhook_secret.

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature (constant-time comparison).

    Used by merchants to verify incoming webhooks.
    """
    expected = sign_payload(payload_bytes, secret)
    return hmac.compare_digest(expected, signature)


# ─── Retry Schedule ─────────────────────────────────────────────────────────

def calculate_next_retry(attempt_count: int) -> datetime | None:
    """Calculate next retry datetime based on attempt count.

    attempt_count is 1-indexed (after first failed attempt).

    Returns:
        Next retry datetime, or None if max attempts exhausted.
    """
    # attempt_count: 1=just failed first, delay index 0=1m
    delay_index = attempt_count - 1

    if delay_index >= len(RETRY_DELAYS):
        return None  # Max attempts exhausted

    delay_seconds = RETRY_DELAYS[delay_index]
    return datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)


# ─── Service ─────────────────────────────────────────────────────────────────

class WebhookService:
    """Webhook dispatch — stateless, operates on provided DB session."""

    # ── Queue Delivery ───────────────────────────────────────────────────

    async def queue_webhook(
        self,
        db: AsyncSession,
        merchant: Merchant,
        event_type: str,
        payload: dict[str, Any],
        invoice_id: uuid.UUID | None = None,
    ) -> WebhookDelivery | None:
        """Create a webhook delivery record for async processing.

        Returns None if merchant has no webhook_url configured.
        Validates URL against TOR_ONLY policy.
        """
        if not merchant.webhook_url or not merchant.webhook_secret:
            logger.debug(
                "Merchant %s has no webhook configured, skipping %s",
                merchant.id,
                event_type,
            )
            return None

        # Validate webhook URL against TOR_ONLY policy
        url_valid, url_error = tor_proxy.validate_webhook_url(merchant.webhook_url)
        if not url_valid:
            logger.warning(
                "Webhook URL rejected for merchant %s: %s",
                merchant.id,
                url_error,
            )
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
            next_retry_at=datetime.now(timezone.utc),  # Immediate first attempt
        )
        db.add(delivery)
        await db.flush()

        logger.info(
            "Webhook queued: %s, event=%s, merchant=%s",
            delivery.id,
            event_type,
            merchant.id,
        )

        return delivery

    # ── Build Payloads ───────────────────────────────────────────────────

    @staticmethod
    def build_payment_payload(
        payment: Payment,
        invoice: Invoice,
    ) -> dict[str, Any]:
        """Build webhook payload for payment events."""
        return {
            "payment": {
                "id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "tx_hash": payment.tx_hash,
                "amount_atomic": payment.amount_atomic,
                "amount_xmr": str(payment.amount_xmr),
                "status": payment.status.value,
                "confirmations": payment.confirmations,
                "block_height": payment.block_height,
                "detected_at": payment.detected_at.isoformat() if payment.detected_at else None,
                "confirmed_at": payment.confirmed_at.isoformat() if payment.confirmed_at else None,
            },
            "invoice": {
                "id": str(invoice.id),
                "status": invoice.status.value,
                "amount_atomic": invoice.amount_atomic,
                "amount_xmr": str(invoice.amount_xmr),
                "description": invoice.description,
            },
        }

    @staticmethod
    def build_invoice_payload(invoice: Invoice) -> dict[str, Any]:
        """Build webhook payload for invoice-only events."""
        return {
            "invoice": {
                "id": str(invoice.id),
                "status": invoice.status.value,
                "amount_atomic": invoice.amount_atomic,
                "amount_xmr": str(invoice.amount_xmr),
                "fiat_amount": str(invoice.fiat_amount) if invoice.fiat_amount else None,
                "fiat_currency": invoice.fiat_currency,
                "description": invoice.description,
                "expires_at": invoice.expires_at.isoformat() if invoice.expires_at else None,
                "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            },
        }

    @staticmethod
    def build_subscription_payload(
        event_type: str,
        subscription: Subscription,
        invoice_id: uuid.UUID | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Build webhook payload for subscription events."""
        payload: dict[str, Any] = {
            "subscription": {
                "id": str(subscription.id),
                "merchant_id": str(subscription.merchant_id),
                "customer_id": str(subscription.customer_id),
                "status": subscription.status.value if hasattr(subscription.status, 'value') else str(subscription.status),
                "amount_atomic": subscription.amount_atomic,
                "amount_xmr": str(subscription.amount_xmr),
                "interval_days": subscription.interval_days,
                "next_due_at": subscription.next_due_at.isoformat() if subscription.next_due_at else None,
                "created_at": subscription.created_at.isoformat(),
            },
        }
        if invoice_id:
            payload["invoice_id"] = str(invoice_id)
        if period_start:
            payload["period_start"] = period_start.isoformat()
        if period_end:
            payload["period_end"] = period_end.isoformat()
        if reason:
            payload["reason"] = reason
        return payload

    # ── Dispatch Events ──────────────────────────────────────────────────

    async def dispatch_events(
        self,
        db: AsyncSession,
        events: list[str],
        merchant: Merchant,
        invoice: Invoice,
        payment: Payment | None = None,
    ) -> list[WebhookDelivery]:
        """Queue webhook deliveries for payment/invoice events.

        Args:
            events: List of event type strings.
            merchant: Merchant object (must have webhook_url, webhook_secret).
            invoice: Invoice related to the events.
            payment: Payment object (required for payment.* events).

        Returns:
            List of created WebhookDelivery records.
        """
        deliveries: list[WebhookDelivery] = []

        for event_type in events:
            if event_type.startswith("payment.") and payment is not None:
                payload = self.build_payment_payload(payment, invoice)
            else:
                payload = self.build_invoice_payload(invoice)

            # Add event metadata
            payload["event"] = event_type
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()

            delivery = await self.queue_webhook(
                db=db,
                merchant=merchant,
                event_type=event_type,
                payload=payload,
                invoice_id=invoice.id,
            )
            if delivery:
                deliveries.append(delivery)

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
        """Queue a single subscription webhook event.

        Loads merchant from DB. Returns None if no webhook configured.
        """
        from app.db.models import Merchant as MerchantModel
        from sqlalchemy import select as sa_select

        merchant_stmt = sa_select(MerchantModel).where(
            MerchantModel.id == subscription.merchant_id
        )
        merchant = (await db.execute(merchant_stmt)).scalar_one_or_none()
        if merchant is None:
            return None

        payload = self.build_subscription_payload(
            event_type=event_type,
            subscription=subscription,
            invoice_id=invoice_id,
            period_start=period_start,
            period_end=period_end,
            reason=reason,
        )
        payload["event"] = event_type
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        return await self.queue_webhook(
            db=db,
            merchant=merchant,
            event_type=event_type,
            payload=payload,
        )

    # ── Attempt Delivery ─────────────────────────────────────────────────

    async def attempt_delivery(
        self,
        delivery: WebhookDelivery,
        webhook_secret: str,
    ) -> bool:
        """Attempt to deliver a single webhook.

        Sends HTTP POST with HMAC-SHA256 signature.
        Routes through Tor SOCKS5 proxy if enabled.
        Returns True if delivery succeeded (2xx response).
        """
        # Random jitter (metadata protection)
        jitter = random.uniform(JITTER_MIN, JITTER_MAX)
        await asyncio.sleep(jitter)

        # Serialize payload
        payload_bytes = json.dumps(
            delivery.payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

        # Sign
        signature = sign_payload(payload_bytes, webhook_secret)

        # Headers
        headers = {
            "Content-Type": "application/json",
            "X-GhostBill-Signature": signature,
            "X-GhostBill-Event-ID": str(delivery.id),
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

            if success:
                logger.info(
                    "Webhook delivered: %s, event=%s, status=%d, tor=%s",
                    delivery.id,
                    delivery.event_type,
                    response.status_code,
                    tor_proxy.enabled,
                )
            else:
                logger.warning(
                    "Webhook failed: %s, event=%s, status=%d",
                    delivery.id,
                    delivery.event_type,
                    response.status_code,
                )

            return success

        except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
            delivery.response_code = None
            delivery.response_body = str(exc)[:2048]

            logger.warning(
                "Webhook delivery error: %s, event=%s, error=%s",
                delivery.id,
                delivery.event_type,
                str(exc),
            )
            return False

    # ── Get Pending Deliveries ───────────────────────────────────────────

    async def get_pending_deliveries(
        self,
        db: AsyncSession,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        """Get webhook deliveries ready for (re)delivery.

        Returns deliveries where:
            - status = pending
            - next_retry_at <= NOW()
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookStatus.pending,
                WebhookDelivery.next_retry_at <= now,
            )
            .order_by(WebhookDelivery.next_retry_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── Process Delivery Result ──────────────────────────────────────────

    async def process_delivery_result(
        self,
        db: AsyncSession,
        delivery: WebhookDelivery,
        success: bool,
    ) -> None:
        """Update delivery record after an attempt.

        If success: mark as delivered.
        If failure: increment attempts, calculate next retry or mark as failed.
        """
        delivery.attempts += 1
        delivery.last_attempt_at = datetime.now(timezone.utc)

        if success:
            delivery.status = WebhookStatus.delivered
            delivery.next_retry_at = None
        else:
            if delivery.attempts >= delivery.max_attempts:
                delivery.status = WebhookStatus.failed
                delivery.next_retry_at = None

                logger.warning(
                    "Webhook exhausted retries: %s, event=%s, attempts=%d",
                    delivery.id,
                    delivery.event_type,
                    delivery.attempts,
                )
            else:
                next_retry = calculate_next_retry(delivery.attempts)
                delivery.next_retry_at = next_retry

                logger.info(
                    "Webhook retry scheduled: %s, attempt=%d/%d, next=%s",
                    delivery.id,
                    delivery.attempts,
                    delivery.max_attempts,
                    next_retry,
                )

        await db.flush()

    # ── List Deliveries (for API) ────────────────────────────────────────

    async def list_deliveries(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        invoice_id: uuid.UUID | None = None,
        status: WebhookStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[WebhookDelivery], int]:
        """List webhook deliveries for a merchant."""
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        base_where = [WebhookDelivery.merchant_id == merchant_id]
        if invoice_id is not None:
            base_where.append(WebhookDelivery.invoice_id == invoice_id)
        if status is not None:
            base_where.append(WebhookDelivery.status == status)

        count_stmt = select(func.count(WebhookDelivery.id)).where(*base_where)
        total = (await db.execute(count_stmt)).scalar_one()

        data_stmt = (
            select(WebhookDelivery)
            .where(*base_where)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(data_stmt)
        deliveries = list(result.scalars().all())

        return deliveries, total

    # ── Manual Retry ─────────────────────────────────────────────────────

    async def retry_delivery(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery | None:
        """Reset a failed delivery for retry.

        Only failed deliveries can be manually retried.
        Resets status to pending with immediate next_retry_at.
        """
        stmt = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.merchant_id == merchant_id,
            )
        )
        result = await db.execute(stmt)
        delivery = result.scalar_one_or_none()

        if delivery is None:
            return None

        if delivery.status != WebhookStatus.failed:
            return None

        delivery.status = WebhookStatus.pending
        delivery.attempts = 0
        delivery.next_retry_at = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "Webhook retry manually triggered: %s, event=%s",
            delivery.id,
            delivery.event_type,
        )

        return delivery


# ─── Module-level instance ───────────────────────────────────────────────────

webhook_service = WebhookService()
