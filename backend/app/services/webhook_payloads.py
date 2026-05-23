"""Webhook payload builders, HMAC signing, retry schedule, event registry.

Stateless helpers used by webhook_service.py.
"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.db.models import Invoice, Payment, Subscription

MAX_ATTEMPTS: int = 7
DELIVERY_TIMEOUT: float = 10.0
RETRY_DELAYS: list[int] = [60, 300, 1800, 7200, 43200, 86400]
JITTER_MIN: float = 0.05
JITTER_MAX: float = 0.2

# Valid event types (22 total — Wave 3A adds invoice.exception_payment and invoice.reverted)
VALID_EVENTS: list[str] = [
    "payment.detected",
    "payment.confirmed",
    "payment.orphaned",
    "invoice.paid",
    "invoice.expired",
    "invoice.partially_paid",
    "invoice.overpaid",
    "invoice.late_paid",
    "invoice.exception_payment",
    "invoice.reverted",
    "subscription.created",
    "subscription.renewed",
    "subscription.past_due",
    "subscription.cancelled",
    "subscription.payment_confirmed",
    "subscription.updated",  # Phase 6A
    "subscription.paused",  # Phase 6B
    "subscription.resumed",  # Phase 6B
    "subscription.expired",  # Phase 6B
    "subscription.trial_started",  # Phase 8A
    "subscription.trial_ended",  # Phase 8A
    "subscription.prepaid",  # Phase 8B
]


def sign_payload(
    payload_bytes: bytes,
    secret: str,
    timestamp: str | None = None,
    delivery_id: str | None = None,
) -> str:
    if timestamp is not None and delivery_id is not None:
        msg = f"{timestamp}.{delivery_id}.".encode("utf-8") + payload_bytes
    else:
        msg = payload_bytes
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=msg,
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_signature(
    payload_bytes: bytes,
    secret: str,
    signature: str,
    timestamp: str | None = None,
    delivery_id: str | None = None,
) -> bool:
    normalized = signature.lower()
    if timestamp is not None and delivery_id is not None:
        expected = sign_payload(payload_bytes, secret, timestamp, delivery_id).lower()
        if hmac.compare_digest(expected, normalized):
            return True
    return hmac.compare_digest(sign_payload(payload_bytes, secret).lower(), normalized)


def calculate_next_retry(attempt_count: int) -> datetime | None:
    idx = attempt_count - 1
    if idx >= len(RETRY_DELAYS):
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=RETRY_DELAYS[idx])


def build_payment_payload(payment: Payment, invoice: Invoice) -> dict[str, Any]:
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


def build_invoice_payload(invoice: Invoice) -> dict[str, Any]:
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


def build_invoice_exception_payment_payload(invoice: Invoice, payment: Payment) -> dict[str, Any]:
    payload = build_invoice_payload(invoice)
    payload["payment"] = {
        "id": str(payment.id),
        "invoice_id": str(payment.invoice_id),
        "tx_hash": payment.tx_hash,
        "amount_atomic": payment.amount_atomic,
        "amount_xmr": str(payment.amount_xmr),
        "status": payment.status.value,
        "confirmations": payment.confirmations,
        "block_height": payment.block_height,
    }
    payload["exception"] = "cancelled_invoice_payment"
    return payload


def build_invoice_reverted_payload(invoice: Invoice) -> dict[str, Any]:
    payload = build_invoice_payload(invoice)
    payload["reverted"] = True
    return payload


def build_subscription_payload(
    event_type: str,
    subscription: Subscription,
    invoice_id: UUID | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subscription": {
            "id": str(subscription.id),
            "merchant_id": str(subscription.merchant_id),
            "customer_id": str(subscription.customer_id),
            "status": subscription.status.value if hasattr(subscription.status, "value") else str(subscription.status),
            "amount_atomic": subscription.amount_atomic,
            "amount_xmr": str(subscription.amount_xmr),
            "interval_days": subscription.interval_days,
            "next_due_at": subscription.next_due_at.isoformat() if subscription.next_due_at else None,
            "prepaid_until": subscription.prepaid_until.isoformat() if subscription.prepaid_until else None,
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


def build_subscription_updated_payload(subscription: Subscription) -> dict[str, Any]:
    """Phase 6A: payload for subscription.updated event."""
    payload = build_subscription_payload("subscription.updated", subscription)
    payload["subscription"]["current"] = {
        "amount_atomic": subscription.amount_atomic,
        "interval_days": subscription.interval_days,
        "grace_days_soft": subscription.grace_days_soft,
        "grace_days_hard": subscription.grace_days_hard,
    }
    pending = {}
    if subscription.pending_amount_atomic is not None:
        pending["amount_atomic"] = subscription.pending_amount_atomic
        pending["amount_xmr"] = str(subscription.pending_amount_xmr)
    if subscription.pending_interval_days is not None:
        pending["interval_days"] = subscription.pending_interval_days
    if subscription.pending_grace_soft is not None:
        pending["grace_days_soft"] = subscription.pending_grace_soft
    if subscription.pending_grace_hard is not None:
        pending["grace_days_hard"] = subscription.pending_grace_hard
    if pending:
        payload["pending_changes"] = pending
    return payload
