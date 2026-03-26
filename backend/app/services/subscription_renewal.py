"""Subscription renewal logic — invoice creation, pending changes, billing anchor.

Extracted from subscription_service.py for maintainability.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Invoice,
    InvoiceStatus,
    Merchant,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
)
from app.services.invoice_service import invoice_service
from app.services.subscription_exceptions import SkipRenewalError

logger = logging.getLogger(__name__)


# ─── Billing Anchor ────────────────────────────────────────────────────────


def calculate_next_due(anchor: datetime, interval_days: int, now: datetime | None = None) -> datetime:
    """Deterministic next_due from billing anchor. No drift."""
    if now is None:
        now = datetime.now(timezone.utc)
    interval = timedelta(days=interval_days)
    if interval.total_seconds() == 0:
        return now
    elapsed = (now - anchor).total_seconds()
    periods = max(1, ceil(elapsed / interval.total_seconds()))
    return anchor + periods * interval


# ─── Pending Changes ─────────────────────────────────────────────────────


def apply_pending_changes(sub: Subscription) -> bool:
    """Apply pending_* fields to subscription. Returns True if any applied."""
    applied = False
    if sub.pending_amount_atomic is not None:
        sub.amount_atomic = sub.pending_amount_atomic
        sub.amount_xmr = sub.pending_amount_xmr
        sub.pending_amount_atomic = None
        sub.pending_amount_xmr = None
        applied = True
    if sub.pending_interval_days is not None:
        sub.interval_days = sub.pending_interval_days
        sub.pending_interval_days = None
        applied = True
    if sub.pending_grace_soft is not None:
        sub.grace_days_soft = sub.pending_grace_soft
        sub.pending_grace_soft = None
        applied = True
    if sub.pending_grace_hard is not None:
        sub.grace_days_hard = sub.pending_grace_hard
        sub.pending_grace_hard = None
        applied = True
    return applied


# ─── Renewal Invoice ──────────────────────────────────────────────────────


async def create_renewal_invoice(
    db: AsyncSession, sub: Subscription,
) -> tuple[Invoice, SubscriptionPayment] | None:
    """Public wrapper — loads merchant and delegates."""
    merchant_stmt = select(Merchant).where(Merchant.id == sub.merchant_id)
    merchant = (await db.execute(merchant_stmt)).scalar_one_or_none()
    if merchant is None:
        logger.error("Merchant %s not found for sub %s", sub.merchant_id, sub.id)
        return None
    return await _create_renewal_invoice(db, sub, merchant)


async def _create_renewal_invoice(
    db: AsyncSession, sub: Subscription, merchant: Merchant,
) -> tuple[Invoice, SubscriptionPayment]:
    """Create invoice + subscription_payment for one period.

    Applies pending changes and uses billing anchor for next_due.
    """
    period_start = sub.next_due_at
    period_end = period_start + timedelta(days=sub.interval_days)

    # 1. Idempotency
    existing_stmt = select(SubscriptionPayment).where(
        SubscriptionPayment.subscription_id == sub.id,
        SubscriptionPayment.period_start == period_start,
    )
    if (await db.execute(existing_stmt)).scalar_one_or_none() is not None:
        raise SkipRenewalError(f"Already renewed for period {period_start}")

    # 2. Unpaid invoice check
    unpaid_stmt = (
        select(func.count(SubscriptionPayment.id))
        .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
        .where(
            SubscriptionPayment.subscription_id == sub.id,
            Invoice.status.in_([InvoiceStatus.pending, InvoiceStatus.partially_paid]),
        )
    )
    if (await db.execute(unpaid_stmt)).scalar_one() > 0:
        raise SkipRenewalError("Unpaid invoice exists, skipping renewal")

    # 3. Apply pending changes
    changes_applied = apply_pending_changes(sub)
    if changes_applied:
        period_end = period_start + timedelta(days=sub.interval_days)
        logger.info("Pending changes applied for sub %s at renewal", sub.id)

    # 4. Create invoice
    expires_in = (sub.grace_days_soft + sub.grace_days_hard) * 86400
    invoice = await invoice_service.create_invoice(
        db=db, merchant=merchant, amount_xmr_raw=sub.amount_xmr,
        description=f"Subscription {sub.id}",
        expires_in=max(expires_in, 600),
        metadata={"subscription_id": str(sub.id),
                  "period_start": period_start.isoformat(),
                  "period_end": period_end.isoformat()},
    )

    # 5. Link subscription_payment
    sp = SubscriptionPayment(
        id=uuid.uuid4(), subscription_id=sub.id, invoice_id=invoice.id,
        period_start=period_start, period_end=period_end,
    )
    db.add(sp)

    # 6. Advance next_due via billing anchor
    sub.next_due_at = calculate_next_due(
        anchor=sub.billing_anchor_at, interval_days=sub.interval_days,
    )

    # 7. Audit
    db.add(AuditLog(
        merchant_id=sub.merchant_id, action="subscription.renewed",
        entity_type="subscription", entity_id=sub.id,
        details={"invoice_id": str(invoice.id),
                 "period_start": period_start.isoformat(),
                 "period_end": period_end.isoformat(),
                 "pending_applied": changes_applied},
    ))
    await db.flush()

    logger.info("Renewal: sub=%s, invoice=%s, %s→%s",
                sub.id, invoice.id, period_start.date(), period_end.date())
    return invoice, sp
