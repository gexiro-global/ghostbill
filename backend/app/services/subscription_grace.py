"""Subscription grace period checks and payment hook.

Extracted from subscription_service.py for maintainability.

Grace logic:
    soft (3d default): active → past_due
    hard (7d default): past_due → expired
    recovery: past_due with paid invoice → active

Phase 6B: fires subscription.expired event (not cancelled) on hard grace.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Invoice,
    InvoiceStatus,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)


async def handle_subscription_payment(
    db: AsyncSession, invoice_id: uuid.UUID,
) -> None:
    """Called when invoice transitions to paid/overpaid/late_paid.

    Recovers subscription from past_due → active if applicable.
    """
    sp_stmt = select(SubscriptionPayment).where(
        SubscriptionPayment.invoice_id == invoice_id
    )
    sp = (await db.execute(sp_stmt)).scalar_one_or_none()
    if sp is None:
        return

    sub_stmt = (
        select(Subscription)
        .where(Subscription.id == sp.subscription_id)
        .with_for_update()
    )
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    if sub is None:
        return

    if sub.status == SubscriptionStatus.past_due:
        sub.status = SubscriptionStatus.active
        logger.info("Subscription %s: past_due → active (invoice %s paid)", sub.id, invoice_id)

    await db.flush()


async def check_grace_periods(db: AsyncSession) -> dict[str, int]:
    """Check all subscriptions for grace period violations.

    Returns dict: {soft, hard, recovered}.
    """
    now = datetime.now(timezone.utc)
    counts = {"soft": 0, "hard": 0, "recovered": 0}

    # Soft grace: active → past_due
    soft_stmt = (
        select(Subscription)
        .join(SubscriptionPayment, SubscriptionPayment.subscription_id == Subscription.id)
        .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
        .where(
            Subscription.status == SubscriptionStatus.active,
            Invoice.status.in_([InvoiceStatus.pending, InvoiceStatus.partially_paid]),
            SubscriptionPayment.period_start + text(
                "make_interval(days => subscriptions.grace_days_soft)"
            ) < now,
        )
        .group_by(Subscription.id)
    )
    for sub in (await db.execute(soft_stmt)).scalars().all():
        sub.status = SubscriptionStatus.past_due
        counts["soft"] += 1
        logger.info("Subscription %s → past_due (soft grace)", sub.id)

    # Hard grace: past_due → expired (Phase 6B: fires subscription.expired, NOT cancelled)
    hard_stmt = (
        select(Subscription)
        .join(SubscriptionPayment, SubscriptionPayment.subscription_id == Subscription.id)
        .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
        .where(
            Subscription.status == SubscriptionStatus.past_due,
            Invoice.status.in_([InvoiceStatus.pending, InvoiceStatus.partially_paid]),
            SubscriptionPayment.period_start + text(
                "make_interval(days => subscriptions.grace_days_hard)"
            ) < now,
        )
        .group_by(Subscription.id)
    )
    for sub in (await db.execute(hard_stmt)).scalars().all():
        sub.status = SubscriptionStatus.expired
        counts["hard"] += 1
        logger.info("Subscription %s → expired (hard grace)", sub.id)
        # Phase 6B: fire subscription.expired event
        try:
            from app.services.webhook_service import webhook_service
            await webhook_service.dispatch_subscription_event(
                db=db, event_type="subscription.expired",
                subscription=sub, reason="hard_grace_exceeded",
            )
        except Exception as exc:
            logger.warning("Failed to fire subscription.expired for %s: %s", sub.id, exc)

    # Recovery: past_due with paid invoice → active
    recovery_stmt = (
        select(Subscription)
        .join(SubscriptionPayment, SubscriptionPayment.subscription_id == Subscription.id)
        .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
        .where(
            Subscription.status == SubscriptionStatus.past_due,
            Invoice.status.in_([
                InvoiceStatus.paid, InvoiceStatus.overpaid, InvoiceStatus.late_paid,
            ]),
        )
        .group_by(Subscription.id)
    )
    for sub in (await db.execute(recovery_stmt)).scalars().all():
        sub.status = SubscriptionStatus.active
        counts["recovered"] += 1
        logger.info("Subscription %s → active (recovery)", sub.id)

    if any(counts.values()):
        await db.flush()

    return counts
