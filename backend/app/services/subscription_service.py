"""Subscription service — create, get, list, state transitions.

Split modules:
    subscription_update.py — pending changes (PATCH)
    subscription_renewal.py — invoice creation, billing anchor
    subscription_grace.py — grace periods, payment hook
    subscription_exceptions.py — errors, state machine

Phase 6B: fires subscription.paused/resumed webhook events.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Customer,
    Invoice,
    InvoiceStatus,
    Merchant,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
)
from app.services.invoice_service import WalletUnavailableError
from app.services.monero_rpc import xmr_to_atomic
from app.services.subscription_exceptions import (
    TERMINAL_STATUSES,
    SkipRenewalError,
    SubscriptionNotFoundError,
    SubscriptionStateError,
    SubscriptionValidationError,
)
from app.services.subscription_renewal import _create_renewal_invoice

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Subscription lifecycle management."""

    # ── Create ───────────────────────────────────────────────────────

    async def create_subscription(
        self,
        db: AsyncSession,
        merchant: Merchant,
        customer_id: uuid.UUID,
        amount_xmr_raw: str | float | Decimal,
        interval_days: int,
        grace_days_soft: int = 3,
        grace_days_hard: int = 7,
        start_at: datetime | None = None,
        trial_days: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Subscription:
        """Create new subscription and optionally first invoice."""
        cust = (
            await db.execute(select(Customer).where(Customer.id == customer_id, Customer.merchant_id == merchant.id))
        ).scalar_one_or_none()
        if cust is None:
            raise SubscriptionNotFoundError(f"Customer {customer_id} not found.")

        try:
            amount_xmr = Decimal(str(amount_xmr_raw))
        except (InvalidOperation, ValueError, TypeError):
            raise SubscriptionValidationError(f"Invalid amount_xmr: {amount_xmr_raw!r}")
        if amount_xmr <= 0:
            raise SubscriptionValidationError("amount_xmr must be greater than 0.")
        if not isinstance(interval_days, int) or interval_days < 1:
            raise SubscriptionValidationError("interval_days must be >= 1.")
        if grace_days_soft < 0 or grace_days_hard < 0:
            raise SubscriptionValidationError("Grace days cannot be negative.")
        if grace_days_hard < grace_days_soft:
            raise SubscriptionValidationError("grace_days_hard must be >= grace_days_soft.")

        now = datetime.now(timezone.utc)
        next_due = start_at if start_at else now

        # Phase 8A: Trial period handling
        is_trial = trial_days is not None and trial_days > 0
        if is_trial:
            initial_status = SubscriptionStatus.trialing
            trial_end = now + timedelta(days=trial_days)
        else:
            initial_status = SubscriptionStatus.active
            trial_end = None

        sub = Subscription(
            id=uuid.uuid4(),
            merchant_id=merchant.id,
            customer_id=customer_id,
            amount_xmr=amount_xmr,
            amount_atomic=xmr_to_atomic(amount_xmr),
            interval_days=interval_days,
            status=initial_status,
            grace_days_soft=grace_days_soft,
            grace_days_hard=grace_days_hard,
            next_due_at=trial_end if is_trial else next_due,
            metadata_json=metadata,
            billing_anchor_at=next_due,
            trial_days=trial_days if is_trial else None,
            trial_end_at=trial_end,
        )
        db.add(sub)
        await db.flush()

        logger.info(
            "Subscription created: %s, merchant=%s, amount=%s XMR, trial=%s",
            sub.id,
            merchant.id,
            amount_xmr,
            trial_days if is_trial else "none",
        )

        if is_trial:
            await self._fire_lifecycle_event(db, "subscription.trial_started", sub)
        elif next_due <= now:
            try:
                await _create_renewal_invoice(db, sub, merchant)
            except (WalletUnavailableError, SkipRenewalError) as exc:
                logger.warning("First invoice failed for sub %s: %s", sub.id, exc)

        return sub

    # ── Get / List ────────────────────────────────────────────────────

    async def get_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> dict:
        """Get subscription with customer info and payment history."""
        sub = (
            await db.execute(
                select(Subscription).where(Subscription.id == subscription_id, Subscription.merchant_id == merchant_id)
            )
        ).scalar_one_or_none()
        if sub is None:
            raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found.")

        customer = (await db.execute(select(Customer).where(Customer.id == sub.customer_id))).scalar_one_or_none()

        sp_stmt = (
            select(SubscriptionPayment, Invoice.status, Invoice.paid_at)
            .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
            .where(SubscriptionPayment.subscription_id == subscription_id)
            .order_by(SubscriptionPayment.period_start.desc())
        )
        payments = []
        for sp, inv_status, inv_paid_at in (await db.execute(sp_stmt)).all():
            payments.append(
                {
                    "id": str(sp.id),
                    "period_start": sp.period_start.isoformat(),
                    "period_end": sp.period_end.isoformat(),
                    "invoice_id": str(sp.invoice_id),
                    "invoice_status": inv_status.value,
                    "paid_at": inv_paid_at.isoformat() if inv_paid_at else None,
                }
            )

        return {
            "subscription": sub,
            "customer": {"id": str(customer.id), "external_id": customer.external_id, "email": customer.email}
            if customer
            else None,
            "payments": payments,
        }

    async def list_subscriptions(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        status: SubscriptionStatus | None = None,
        customer_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Subscription], int]:
        """List subscriptions with optional filters."""
        limit, offset = max(1, min(limit, 100)), max(0, offset)
        where = [Subscription.merchant_id == merchant_id]
        if status is not None:
            where.append(Subscription.status == status)
        if customer_id is not None:
            where.append(Subscription.customer_id == customer_id)

        total = (await db.execute(select(func.count(Subscription.id)).where(*where))).scalar_one()
        subs = list(
            (
                await db.execute(
                    select(Subscription)
                    .where(*where)
                    .order_by(Subscription.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return subs, total

    # ── State Transitions (with webhook events) ───────────────────

    async def pause_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        sub = await self._get_for_update(db, merchant_id, subscription_id)
        if sub.status != SubscriptionStatus.active:
            raise SubscriptionStateError(f"Cannot pause subscription with status '{sub.status.value}'.")
        sub.status = SubscriptionStatus.paused
        await db.flush()
        # Phase 6B: fire subscription.paused event
        await self._fire_lifecycle_event(db, "subscription.paused", sub, reason="merchant_action")
        return sub

    async def resume_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        sub = await self._get_for_update(db, merchant_id, subscription_id)
        if sub.status != SubscriptionStatus.paused:
            raise SubscriptionStateError(f"Cannot resume subscription with status '{sub.status.value}'.")
        now = datetime.now(timezone.utc)
        if sub.next_due_at and sub.next_due_at < now:
            sub.next_due_at = now
        sub.status = SubscriptionStatus.active
        await db.flush()
        # Phase 6B: fire subscription.resumed event
        await self._fire_lifecycle_event(db, "subscription.resumed", sub, reason="merchant_action")
        return sub

    async def cancel_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        from app.services.invoice_service import invoice_service as inv_svc

        sub = await self._get_for_update(db, merchant_id, subscription_id)
        if sub.status in TERMINAL_STATUSES:
            raise SubscriptionStateError(f"Subscription is already {sub.status.value}.")
        sub.status = SubscriptionStatus.cancelled
        sub.cancelled_at = datetime.now(timezone.utc)
        sp_stmt = (
            select(SubscriptionPayment)
            .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
            .where(SubscriptionPayment.subscription_id == sub.id, Invoice.status == InvoiceStatus.pending)
        )
        for sp in (await db.execute(sp_stmt)).scalars().all():
            try:
                await inv_svc.cancel_invoice(db, merchant_id, sp.invoice_id)
            except Exception as exc:
                logger.warning("Failed to cancel invoice %s: %s", sp.invoice_id, exc)
        await db.flush()
        return sub

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_for_update(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        stmt = (
            select(Subscription)
            .where(Subscription.id == subscription_id, Subscription.merchant_id == merchant_id)
            .with_for_update()
        )
        sub = (await db.execute(stmt)).scalar_one_or_none()
        if sub is None:
            raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found.")
        return sub

    async def _fire_lifecycle_event(
        self,
        db: AsyncSession,
        event_type: str,
        sub: Subscription,
        reason: str | None = None,
    ) -> None:
        """Fire a subscription lifecycle webhook event."""
        try:
            from app.services.webhook_service import webhook_service

            await webhook_service.dispatch_subscription_event(
                db=db, event_type=event_type, subscription=sub, reason=reason
            )
        except Exception as exc:
            logger.warning("Failed to fire %s for sub %s: %s", event_type, sub.id, exc)


subscription_service = SubscriptionService()
