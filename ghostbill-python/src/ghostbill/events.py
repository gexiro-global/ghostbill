"""Webhook event constants from backend/app/services/webhook_payloads.py for server v1.3-rc3.

The server code currently defines 22 events. docs/WEBHOOKS.md currently documents only 20 events; that drift is a
backlog item, and the SDK follows the code source of truth.
"""

from __future__ import annotations

__all__ = [
    "ALL_EVENTS",
    "INVOICE_EXCEPTION_PAYMENT",
    "INVOICE_EXPIRED",
    "INVOICE_LATE_PAID",
    "INVOICE_OVERPAID",
    "INVOICE_PAID",
    "INVOICE_PARTIALLY_PAID",
    "INVOICE_REVERTED",
    "PAYMENT_CONFIRMED",
    "PAYMENT_DETECTED",
    "PAYMENT_ORPHANED",
    "SUBSCRIPTION_CANCELLED",
    "SUBSCRIPTION_CREATED",
    "SUBSCRIPTION_EXPIRED",
    "SUBSCRIPTION_PAST_DUE",
    "SUBSCRIPTION_PAUSED",
    "SUBSCRIPTION_PAYMENT_CONFIRMED",
    "SUBSCRIPTION_PREPAID",
    "SUBSCRIPTION_RENEWED",
    "SUBSCRIPTION_RESUMED",
    "SUBSCRIPTION_TRIAL_ENDED",
    "SUBSCRIPTION_TRIAL_STARTED",
    "SUBSCRIPTION_UPDATED",
]

# Payment
PAYMENT_DETECTED = "payment.detected"
PAYMENT_CONFIRMED = "payment.confirmed"
PAYMENT_ORPHANED = "payment.orphaned"

# Invoice
INVOICE_PAID = "invoice.paid"
INVOICE_EXPIRED = "invoice.expired"
INVOICE_PARTIALLY_PAID = "invoice.partially_paid"
INVOICE_OVERPAID = "invoice.overpaid"
INVOICE_LATE_PAID = "invoice.late_paid"
INVOICE_EXCEPTION_PAYMENT = "invoice.exception_payment"
INVOICE_REVERTED = "invoice.reverted"

# Subscription
SUBSCRIPTION_CREATED = "subscription.created"
SUBSCRIPTION_RENEWED = "subscription.renewed"
SUBSCRIPTION_PAST_DUE = "subscription.past_due"
SUBSCRIPTION_CANCELLED = "subscription.cancelled"
SUBSCRIPTION_PAYMENT_CONFIRMED = "subscription.payment_confirmed"
SUBSCRIPTION_UPDATED = "subscription.updated"
SUBSCRIPTION_PAUSED = "subscription.paused"
SUBSCRIPTION_RESUMED = "subscription.resumed"
SUBSCRIPTION_EXPIRED = "subscription.expired"
SUBSCRIPTION_TRIAL_STARTED = "subscription.trial_started"
SUBSCRIPTION_TRIAL_ENDED = "subscription.trial_ended"
SUBSCRIPTION_PREPAID = "subscription.prepaid"

ALL_EVENTS: frozenset[str] = frozenset(
    {
        PAYMENT_DETECTED,
        PAYMENT_CONFIRMED,
        PAYMENT_ORPHANED,
        INVOICE_PAID,
        INVOICE_EXPIRED,
        INVOICE_PARTIALLY_PAID,
        INVOICE_OVERPAID,
        INVOICE_LATE_PAID,
        INVOICE_EXCEPTION_PAYMENT,
        INVOICE_REVERTED,
        SUBSCRIPTION_CREATED,
        SUBSCRIPTION_RENEWED,
        SUBSCRIPTION_PAST_DUE,
        SUBSCRIPTION_CANCELLED,
        SUBSCRIPTION_PAYMENT_CONFIRMED,
        SUBSCRIPTION_UPDATED,
        SUBSCRIPTION_PAUSED,
        SUBSCRIPTION_RESUMED,
        SUBSCRIPTION_EXPIRED,
        SUBSCRIPTION_TRIAL_STARTED,
        SUBSCRIPTION_TRIAL_ENDED,
        SUBSCRIPTION_PREPAID,
    }
)
