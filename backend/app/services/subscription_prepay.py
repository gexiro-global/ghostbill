"""Subscription pre-payment service — Phase 8B.

Handles:
    - Prepay invoice creation (N periods with discount)
    - Prepay payment processing (create N subscription_payments, advance next_due)
    - Prepay expiration cleanup (clear prepay fields)
"""

import logging
import uuid
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Invoice,
    Merchant,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
)
from app.services.invoice_service import invoice_service
from app.services.monero_rpc import xmr_to_atomic
from app.services.subscription_exceptions import (
    SubscriptionNotFoundError,
    SubscriptionStateError,
    SubscriptionValidationError,
)
from app.services.subscription_renewal import log_renewal_event

logger = logging.getLogger(__name__)

ALLOWED_PREPAY_STATUSES = {
    SubscriptionStatus.active,
    SubscriptionStatus.past_due,
}


def _find_plan(merchant: Merchant, periods: int) -> dict | None:
    """Find matching prepay plan from merchant config."""
    if not merchant.prepay_plans or not isinstance(merchant.prepay_plans, list):
        return None
    for plan in merchant.prepay_plans:
        if isinstance(plan, dict) and plan.get("periods") == periods:
            return plan
    return None


def _calculate_prepay_amount(
    per_period_xmr: Decimal,
    periods: int,
    discount_pct: int,
) -> tuple[Decimal, int]:
    """Calculate total XMR and atomic amount for prepay invoice.

    Returns (total_xmr, total_atomic).
    """
    total_xmr = per_period_xmr * periods
    if discount_pct > 0:
        discount_factor = Decimal(100 - discount_pct) / Decimal(100)
        total_xmr = (total_xmr * discount_factor).quantize(
            Decimal("0.000000000001"),
            rounding=ROUND_DOWN,
        )
    total_atomic = xmr_to_atomic(total_xmr)
    return total_xmr, total_atomic


async def create_prepay_invoice(
    db: AsyncSession,
    merchant: Merchant,
    subscription_id: uuid.UUID,
    periods: int,
) -> Invoice:
    """Create a prepay invoice for N periods with optional discount.

    Sets subscription.prepay_invoice_id and .prepaid_until to block renewer.
    """
    # 1. Load and validate subscription
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.id == subscription_id,
            Subscription.merchant_id == merchant.id,
        )
        .with_for_update()
    )
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    if sub is None:
        raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found.")

    if sub.status not in ALLOWED_PREPAY_STATUSES:
        raise SubscriptionStateError(
            f"Cannot prepay subscription with status '{sub.status.value}'. "
            f"Allowed: {', '.join(s.value for s in ALLOWED_PREPAY_STATUSES)}."
        )

    if sub.prepay_invoice_id is not None:
        raise SubscriptionStateError("Subscription already has a pending prepay invoice.")

    # 2. Find and validate plan
    if periods < 1:
        raise SubscriptionValidationError("periods must be >= 1.")

    plan = _find_plan(merchant, periods)
    if plan is None:
        raise SubscriptionValidationError(
            f"No prepay plan configured for {periods} periods. Configure plans via PATCH /v1/merchants/me."
        )

    discount_pct = plan.get("discount_pct", 0)
    if not isinstance(discount_pct, (int, float)) or discount_pct < 0 or discount_pct > 99:
        raise SubscriptionValidationError(f"Invalid discount_pct in plan: {discount_pct}")

    # 3. Calculate amount
    total_xmr, total_atomic = _calculate_prepay_amount(
        sub.amount_xmr,
        periods,
        int(discount_pct),
    )

    # 4. Create invoice
    expires_in = max(periods * sub.interval_days * 86400, 86400)  # at least 1 day
    expires_in = min(expires_in, 30 * 86400)  # cap at 30 days

    invoice = await invoice_service.create_invoice(
        db=db,
        merchant=merchant,
        amount_xmr_raw=total_xmr,
        description=f"Prepay {periods}x for subscription {sub.id}",
        expires_in=expires_in,
        metadata={
            "prepay": True,
            "subscription_id": str(sub.id),
            "periods": periods,
            "discount_pct": int(discount_pct),
            "per_period_amount_atomic": sub.amount_atomic,
            "per_period_amount_xmr": str(sub.amount_xmr),
        },
    )

    # 5. Set prepay guard on subscription
    prepaid_end = sub.next_due_at + timedelta(days=periods * sub.interval_days)
    sub.prepay_invoice_id = invoice.id
    sub.prepaid_until = prepaid_end

    # 6. Audit
    db.add(
        AuditLog(
            merchant_id=merchant.id,
            action="subscription.prepay_created",
            entity_type="subscription",
            entity_id=sub.id,
            details={
                "invoice_id": str(invoice.id),
                "periods": periods,
                "discount_pct": int(discount_pct),
                "total_xmr": str(total_xmr),
                "total_atomic": total_atomic,
            },
        )
    )

    await log_renewal_event(
        db,
        sub.id,
        "prepay_created",
        invoice_id=invoice.id,
        details={"periods": periods, "discount_pct": int(discount_pct)},
    )

    await db.flush()

    logger.info(
        "Prepay invoice created: sub=%s, invoice=%s, %dx, -%d%%, total=%s XMR",
        sub.id,
        invoice.id,
        periods,
        discount_pct,
        total_xmr,
    )
    return invoice


async def handle_prepay_payment(
    db: AsyncSession,
    invoice: Invoice,
    sub: Subscription,
) -> None:
    """Process a paid prepay invoice.

    Creates N subscription_payment records and advances next_due_at.
    Called from subscription_grace.handle_subscription_payment.
    """
    meta = invoice.metadata_json or {}
    periods = meta.get("periods", 1)
    discount_pct = meta.get("discount_pct", 0)

    # Create N subscription_payment records
    current_start = sub.next_due_at
    for i in range(periods):
        period_start = current_start + timedelta(days=i * sub.interval_days)
        period_end = current_start + timedelta(days=(i + 1) * sub.interval_days)
        sp = SubscriptionPayment(
            id=uuid.uuid4(),
            subscription_id=sub.id,
            invoice_id=invoice.id,
            period_start=period_start,
            period_end=period_end,
        )
        db.add(sp)

    # Advance next_due_at
    new_next_due = current_start + timedelta(days=periods * sub.interval_days)
    sub.next_due_at = new_next_due
    sub.prepaid_until = new_next_due
    sub.prepay_invoice_id = None  # Clear — prepay fulfilled

    # Recover from past_due if applicable
    if sub.status == SubscriptionStatus.past_due:
        sub.status = SubscriptionStatus.active
        logger.info("Subscription %s: past_due → active (prepay payment)", sub.id)

    # Audit
    db.add(
        AuditLog(
            merchant_id=sub.merchant_id,
            action="subscription.prepay_fulfilled",
            entity_type="subscription",
            entity_id=sub.id,
            details={
                "invoice_id": str(invoice.id),
                "periods": periods,
                "discount_pct": discount_pct,
                "new_next_due": new_next_due.isoformat(),
            },
        )
    )

    await log_renewal_event(
        db,
        sub.id,
        "prepay_fulfilled",
        invoice_id=invoice.id,
        details={
            "periods": periods,
            "new_next_due": new_next_due.isoformat(),
        },
    )

    await db.flush()

    logger.info(
        "Prepay fulfilled: sub=%s, %d periods, next_due=%s",
        sub.id,
        periods,
        new_next_due.date(),
    )


async def clear_expired_prepay(
    db: AsyncSession,
    sub: Subscription,
) -> None:
    """Clear prepay fields when prepay invoice expired/cancelled.

    Called from subscription_renewer when prepay_invoice_id points
    to a non-pending invoice.
    """
    sub.prepay_invoice_id = None
    sub.prepaid_until = None
    await db.flush()
    logger.info("Cleared expired prepay for subscription %s", sub.id)
