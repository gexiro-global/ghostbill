"""Subscription renewal logic — invoice creation, pending changes, billing anchor.

Extracted from subscription_service.py for maintainability.
Phase 6C: event logging via log_renewal_event() helper.
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
    SubscriptionRenewalEvent,
)
from app.services.invoice_service import invoice_service
from app.services.subscription_exceptions import SkipRenewalError

logger = logging.getLogger(__name__)


# ── Renewal Event Logger (Phase 6C) ─────────────────────────────────


async def log_renewal_event(
    db: AsyncSession,
    subscription_id: uuid.UUID,
    result: str,
    invoice_id: uuid.UUID | None = None,
    error_message: str | None = None,
    details: dict | None = None,
) -> None:
    """Insert renewal event log entry. Reusable across renewer + grace."""
    event = SubscriptionRenewalEvent(
        subscription_id=subscription_id,
        result=result,
        invoice_id=invoice_id,
        error_message=error_message,
        details=details or {},
    )
    db.add(event)
    await db.flush()


# ── Billing Anchor ───────────────────────────────────────────────────────


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


def calculate_skipped_periods(period_start: datetime, next_due: datetime, interval_days: int) -> int:
    """Return billable intervals skipped when renewal advances beyond the next period."""
    interval = timedelta(days=interval_days)
    if interval.total_seconds() <= 0:
        return 0
    periods_advanced = int((next_due - period_start).total_seconds() // interval.total_seconds())
    return max(0, periods_advanced - 1)


# ── Pending Changes ─────────────────────────────────────────────────────


def apply_pending_changes(sub: Subscription) -> dict | None:
    """Apply pending_* fields to subscription.

    Returns dict of changes applied (for event logging) or None.
    """
    changes = {}
    if sub.pending_amount_atomic is not None:
        changes["old_amount_atomic"] = sub.amount_atomic
        changes["new_amount_atomic"] = sub.pending_amount_atomic
        sub.amount_atomic = sub.pending_amount_atomic
        sub.amount_xmr = sub.pending_amount_xmr
        sub.pending_amount_atomic = None
        sub.pending_amount_xmr = None
    if sub.pending_interval_days is not None:
        changes["old_interval_days"] = sub.interval_days
        changes["new_interval_days"] = sub.pending_interval_days
        sub.interval_days = sub.pending_interval_days
        sub.pending_interval_days = None
    if sub.pending_grace_soft is not None:
        changes["old_grace_soft"] = sub.grace_days_soft
        changes["new_grace_soft"] = sub.pending_grace_soft
        sub.grace_days_soft = sub.pending_grace_soft
        sub.pending_grace_soft = None
    if sub.pending_grace_hard is not None:
        changes["old_grace_hard"] = sub.grace_days_hard
        changes["new_grace_hard"] = sub.pending_grace_hard
        sub.grace_days_hard = sub.pending_grace_hard
        sub.pending_grace_hard = None
    return changes if changes else None


# ── Renewal Invoice ──────────────────────────────────────────────────────


async def create_renewal_invoice(
    db: AsyncSession,
    sub: Subscription,
) -> tuple[Invoice, SubscriptionPayment] | None:
    """Public wrapper — loads merchant and delegates."""
    merchant_stmt = select(Merchant).where(Merchant.id == sub.merchant_id)
    merchant = (await db.execute(merchant_stmt)).scalar_one_or_none()
    if merchant is None:
        logger.error("Merchant %s not found for sub %s", sub.merchant_id, sub.id)
        return None
    return await _create_renewal_invoice(db, sub, merchant)


async def _create_renewal_invoice(
    db: AsyncSession,
    sub: Subscription,
    merchant: Merchant,
) -> tuple[Invoice, SubscriptionPayment]:
    """Create invoice + subscription_payment for one period.

    Applies pending changes and uses billing anchor for next_due.
    Phase 6C: logs renewal events for success, skip, pending_applied.
    """
    period_start = sub.next_due_at
    period_end = period_start + timedelta(days=sub.interval_days)

    # 1. Idempotency
    existing_stmt = select(SubscriptionPayment).where(
        SubscriptionPayment.subscription_id == sub.id,
        SubscriptionPayment.period_start == period_start,
    )
    if (await db.execute(existing_stmt)).scalar_one_or_none() is not None:
        raise SkipRenewalError(
            f"Already renewed for period {period_start}",
            result_type="skipped_idempotent",
        )

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
        raise SkipRenewalError(
            "Unpaid invoice exists, skipping renewal",
            result_type="skipped_unpaid",
        )

    # 3. Apply pending changes
    applied_changes = apply_pending_changes(sub)
    if applied_changes:
        period_end = period_start + timedelta(days=sub.interval_days)
        logger.info("Pending changes applied for sub %s at renewal", sub.id)
        await log_renewal_event(
            db,
            sub.id,
            "pending_applied",
            details=applied_changes,
        )

    # 4. Create invoice
    expires_in = (sub.grace_days_soft + sub.grace_days_hard) * 86400
    invoice = await invoice_service.create_invoice(
        db=db,
        merchant=merchant,
        amount_xmr_raw=sub.amount_xmr,
        description=f"Subscription {sub.id}",
        expires_in=max(expires_in, 600),
        metadata={
            "subscription_id": str(sub.id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        },
    )

    # 5. Link subscription_payment
    sp = SubscriptionPayment(
        id=uuid.uuid4(),
        subscription_id=sub.id,
        invoice_id=invoice.id,
        period_start=period_start,
        period_end=period_end,
    )
    db.add(sp)

    # 6. Advance next_due via billing anchor
    next_due_at = calculate_next_due(
        anchor=sub.billing_anchor_at,
        interval_days=sub.interval_days,
    )
    skipped_periods = calculate_skipped_periods(period_start, next_due_at, sub.interval_days)
    sub.next_due_at = next_due_at

    if skipped_periods > 0:
        logger.warning(
            "Renewal skipped %d billable periods: sub=%s, period_start=%s, next_due_at=%s",
            skipped_periods,
            sub.id,
            period_start.isoformat(),
            next_due_at.isoformat(),
        )

    # 7. Audit
    db.add(
        AuditLog(
            merchant_id=sub.merchant_id,
            action="subscription.renewed",
            entity_type="subscription",
            entity_id=sub.id,
            details={
                "invoice_id": str(invoice.id),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "pending_applied": applied_changes is not None,
                "skipped_periods": skipped_periods,
            },
        )
    )

    # 8. Phase 6C: log success event
    await log_renewal_event(
        db,
        sub.id,
        "success",
        invoice_id=invoice.id,
        details={
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "amount_atomic": sub.amount_atomic,
            "skipped_periods": skipped_periods,
        },
    )

    await db.flush()

    logger.info("Renewal: sub=%s, invoice=%s, %s→%s", sub.id, invoice.id, period_start.date(), period_end.date())
    return invoice, sp
