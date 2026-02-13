"""
Subscription business logic — create, pause, resume, cancel, renewal, grace.

State machine (5 statuses):
    active → paused, past_due, cancelled
    paused → active, cancelled
    past_due → active, expired, cancelled
    cancelled → (terminal)
    expired → (terminal)

CRITICAL:
    - amount_atomic (BIGINT, piconero) = source of truth
    - Price lock at invoice creation (NOT subscription creation)
    - NEVER stack unpaid invoices — one unpaid = skip renewal
    - UNIQUE(subscription_id, period_start) — prevents double billing
    - FOR UPDATE SKIP LOCKED — safe concurrent access with renewer
    - Grace: soft 3d → past_due, hard 7d → expired
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Customer,
    Invoice,
    InvoiceStatus,
    Merchant,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
)
from app.services.invoice_service import (
    InvoiceService,
    WalletUnavailableError,
    invoice_service,
)
from app.services.monero_rpc import xmr_to_atomic

logger = logging.getLogger(__name__)

# ─── State Machine ──────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[SubscriptionStatus, list[SubscriptionStatus]] = {
    SubscriptionStatus.active: [
        SubscriptionStatus.paused,
        SubscriptionStatus.past_due,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.paused: [
        SubscriptionStatus.active,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.past_due: [
        SubscriptionStatus.active,
        SubscriptionStatus.expired,
        SubscriptionStatus.cancelled,
    ],
    SubscriptionStatus.cancelled: [],
    SubscriptionStatus.expired: [],
}

TERMINAL_STATUSES: set[SubscriptionStatus] = {
    SubscriptionStatus.cancelled,
    SubscriptionStatus.expired,
}


# ─── Exceptions ──────────────────────────────────────────────────────────────

class SubscriptionError(Exception):
    """Base subscription service error."""
    pass


class SubscriptionNotFoundError(SubscriptionError):
    """Subscription not found or wrong merchant."""
    pass


class SubscriptionValidationError(SubscriptionError):
    """Input validation failed."""
    pass


class SubscriptionStateError(SubscriptionError):
    """Invalid state transition."""
    pass


class SkipRenewalError(SubscriptionError):
    """Renewal skipped — unpaid invoice exists or already renewed."""
    pass


# ─── Service ─────────────────────────────────────────────────────────────────

class SubscriptionService:
    """Subscription lifecycle management."""

    @staticmethod
    def can_transition(current: SubscriptionStatus, target: SubscriptionStatus) -> bool:
        return target in VALID_TRANSITIONS.get(current, [])

    # ── Create ───────────────────────────────────────────────────────────

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
        metadata: dict[str, Any] | None = None,
    ) -> Subscription:
        """Create new subscription and optionally first invoice.

        Raises:
            SubscriptionValidationError: Invalid input.
            SubscriptionNotFoundError: Customer not found or wrong merchant.
            WalletUnavailableError: wallet-rpc unavailable for first invoice.
        """
        # 1. Validate customer ownership
        cust_stmt = select(Customer).where(
            Customer.id == customer_id,
            Customer.merchant_id == merchant.id,
        )
        customer = (await db.execute(cust_stmt)).scalar_one_or_none()
        if customer is None:
            raise SubscriptionNotFoundError(
                f"Customer {customer_id} not found."
            )

        # 2. Validate amount
        try:
            amount_xmr = Decimal(str(amount_xmr_raw))
        except (InvalidOperation, ValueError, TypeError):
            raise SubscriptionValidationError(
                f"Invalid amount_xmr: {amount_xmr_raw!r}"
            )
        if amount_xmr <= 0:
            raise SubscriptionValidationError("amount_xmr must be greater than 0.")

        amount_atomic = xmr_to_atomic(amount_xmr)

        # 3. Validate interval
        if not isinstance(interval_days, int) or interval_days < 1:
            raise SubscriptionValidationError("interval_days must be >= 1.")

        # 4. Validate grace periods
        if grace_days_soft < 0 or grace_days_hard < 0:
            raise SubscriptionValidationError("Grace days cannot be negative.")
        if grace_days_hard < grace_days_soft:
            raise SubscriptionValidationError(
                "grace_days_hard must be >= grace_days_soft."
            )

        # 5. Determine next_due_at
        now = datetime.now(timezone.utc)
        next_due = start_at if start_at else now

        # 6. Create subscription
        sub = Subscription(
            id=uuid.uuid4(),
            merchant_id=merchant.id,
            customer_id=customer_id,
            amount_xmr=amount_xmr,
            amount_atomic=amount_atomic,
            interval_days=interval_days,
            status=SubscriptionStatus.active,
            grace_days_soft=grace_days_soft,
            grace_days_hard=grace_days_hard,
            next_due_at=next_due,
            metadata_json=metadata,
        )
        db.add(sub)
        await db.flush()

        logger.info(
            "Subscription created: %s, merchant=%s, customer=%s, amount=%s XMR",
            sub.id, merchant.id, customer_id, amount_xmr,
        )

        # 7. If next_due_at <= now, create first invoice immediately
        if next_due <= now:
            try:
                await self._create_renewal_invoice(db, sub, merchant)
            except (WalletUnavailableError, SkipRenewalError) as exc:
                logger.warning(
                    "First invoice creation failed for sub %s: %s", sub.id, exc
                )
                # Subscription still created — renewer will retry

        return sub

    # ── Get / List ───────────────────────────────────────────────────────

    async def get_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> dict:
        """Get subscription with customer info and payment history.

        Raises SubscriptionNotFoundError if not found.
        Returns enriched dict with nested 'customer' and 'payments'.
        """
        stmt = select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.merchant_id == merchant_id,
        )
        sub = (await db.execute(stmt)).scalar_one_or_none()
        if sub is None:
            raise SubscriptionNotFoundError(
                f"Subscription {subscription_id} not found."
            )

        # Load customer
        cust_stmt = select(Customer).where(Customer.id == sub.customer_id)
        customer = (await db.execute(cust_stmt)).scalar_one_or_none()

        # Load payment history with invoice status
        sp_stmt = (
            select(SubscriptionPayment, Invoice.status, Invoice.paid_at)
            .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
            .where(SubscriptionPayment.subscription_id == subscription_id)
            .order_by(SubscriptionPayment.period_start.desc())
        )
        sp_rows = (await db.execute(sp_stmt)).all()

        payments = []
        for sp, inv_status, inv_paid_at in sp_rows:
            payments.append({
                "id": str(sp.id),
                "period_start": sp.period_start.isoformat(),
                "period_end": sp.period_end.isoformat(),
                "invoice_id": str(sp.invoice_id),
                "invoice_status": inv_status.value,
                "paid_at": inv_paid_at.isoformat() if inv_paid_at else None,
            })

        return {
            "subscription": sub,
            "customer": {
                "id": str(customer.id),
                "external_id": customer.external_id,
                "email": customer.email,
            } if customer else None,
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
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        base_where = [Subscription.merchant_id == merchant_id]
        if status is not None:
            base_where.append(Subscription.status == status)
        if customer_id is not None:
            base_where.append(Subscription.customer_id == customer_id)

        count_stmt = select(func.count(Subscription.id)).where(*base_where)
        total = (await db.execute(count_stmt)).scalar_one()

        data_stmt = (
            select(Subscription)
            .where(*base_where)
            .order_by(Subscription.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(data_stmt)
        subs = list(result.scalars().all())

        return subs, total

    # ── State Transitions ────────────────────────────────────────────────

    async def pause_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        """Pause active subscription.

        Raises SubscriptionStateError if not active.
        """
        sub = await self._get_for_update(db, merchant_id, subscription_id)

        if sub.status != SubscriptionStatus.active:
            raise SubscriptionStateError(
                f"Cannot pause subscription with status '{sub.status.value}'. "
                f"Only active subscriptions can be paused."
            )

        sub.status = SubscriptionStatus.paused
        await db.flush()

        logger.info("Subscription paused: %s", subscription_id)
        return sub

    async def resume_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        """Resume paused subscription.

        Raises SubscriptionStateError if not paused.
        """
        sub = await self._get_for_update(db, merchant_id, subscription_id)

        if sub.status != SubscriptionStatus.paused:
            raise SubscriptionStateError(
                f"Cannot resume subscription with status '{sub.status.value}'. "
                f"Only paused subscriptions can be resumed."
            )

        # Don't generate backlog — if next_due_at is in the past, reset to now
        now = datetime.now(timezone.utc)
        if sub.next_due_at and sub.next_due_at < now:
            sub.next_due_at = now

        sub.status = SubscriptionStatus.active
        await db.flush()

        logger.info("Subscription resumed: %s", subscription_id)
        return sub

    async def cancel_subscription(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        """Cancel subscription. Terminal state.

        Cancels pending invoices linked to this subscription.
        Raises SubscriptionStateError if already terminal.
        """
        sub = await self._get_for_update(db, merchant_id, subscription_id)

        if sub.status in TERMINAL_STATUSES:
            raise SubscriptionStateError(
                f"Subscription is already {sub.status.value}."
            )

        sub.status = SubscriptionStatus.cancelled
        sub.cancelled_at = datetime.now(timezone.utc)

        # Cancel pending invoices linked to this subscription
        sp_stmt = (
            select(SubscriptionPayment)
            .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
            .where(
                SubscriptionPayment.subscription_id == sub.id,
                Invoice.status == InvoiceStatus.pending,
            )
        )
        sp_rows = (await db.execute(sp_stmt)).scalars().all()
        for sp in sp_rows:
            try:
                await invoice_service.cancel_invoice(db, merchant_id, sp.invoice_id)
            except Exception as exc:
                logger.warning(
                    "Failed to cancel invoice %s during sub cancel: %s",
                    sp.invoice_id, exc,
                )

        await db.flush()

        logger.info("Subscription cancelled: %s", subscription_id)
        return sub

    # ── Renewal (called by renewer task) ─────────────────────────────────

    async def create_renewal_invoice(
        self,
        db: AsyncSession,
        sub: Subscription,
    ) -> tuple[Invoice, SubscriptionPayment] | None:
        """Public wrapper for renewal — loads merchant and delegates."""
        merchant_stmt = select(Merchant).where(Merchant.id == sub.merchant_id)
        merchant = (await db.execute(merchant_stmt)).scalar_one_or_none()
        if merchant is None:
            logger.error("Merchant %s not found for sub %s", sub.merchant_id, sub.id)
            return None

        return await self._create_renewal_invoice(db, sub, merchant)

    async def _create_renewal_invoice(
        self,
        db: AsyncSession,
        sub: Subscription,
        merchant: Merchant,
    ) -> tuple[Invoice, SubscriptionPayment]:
        """INTERNAL: create invoice + subscription_payment link for one period.

        Idempotency: UNIQUE(subscription_id, period_start).
        Safety: never stack unpaid invoices.

        Raises:
            SkipRenewalError: Unpaid invoice exists or already renewed.
            WalletUnavailableError: wallet-rpc down.
        """
        period_start = sub.next_due_at
        period_end = period_start + timedelta(days=sub.interval_days)

        # 1. Idempotency check
        existing_stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.subscription_id == sub.id,
            SubscriptionPayment.period_start == period_start,
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise SkipRenewalError(f"Already renewed for period {period_start}")

        # 2. Unpaid invoice check — never stack
        unpaid_stmt = (
            select(func.count(SubscriptionPayment.id))
            .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
            .where(
                SubscriptionPayment.subscription_id == sub.id,
                Invoice.status.in_([InvoiceStatus.pending, InvoiceStatus.partially_paid]),
            )
        )
        unpaid_count = (await db.execute(unpaid_stmt)).scalar_one()
        if unpaid_count > 0:
            raise SkipRenewalError("Unpaid invoice exists, skipping renewal")

        # 3. Create invoice via invoice_service
        expires_in = (sub.grace_days_soft + sub.grace_days_hard) * 86400
        invoice = await invoice_service.create_invoice(
            db=db,
            merchant=merchant,
            amount_xmr_raw=sub.amount_xmr,
            description=f"Subscription {sub.id}",
            expires_in=max(expires_in, 600),  # minimum 10 min
            metadata={
                "subscription_id": str(sub.id),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
        )

        # 4. Create subscription_payment link
        sp = SubscriptionPayment(
            id=uuid.uuid4(),
            subscription_id=sub.id,
            invoice_id=invoice.id,
            period_start=period_start,
            period_end=period_end,
        )
        db.add(sp)

        # 5. Advance next_due_at
        sub.next_due_at = period_end

        # 6. Audit
        audit = AuditLog(
            merchant_id=sub.merchant_id,
            action="subscription.renewed",
            entity_type="subscription",
            entity_id=sub.id,
            details={
                "invoice_id": str(invoice.id),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
        )
        db.add(audit)

        await db.flush()

        logger.info(
            "Renewal invoice created: sub=%s, invoice=%s, period=%s→%s",
            sub.id, invoice.id, period_start.date(), period_end.date(),
        )

        return invoice, sp

    # ── Payment Hook (called by detection engine via payment_service) ────

    async def handle_subscription_payment(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
    ) -> None:
        """Called when invoice transitions to paid/overpaid/late_paid.

        Checks if invoice is linked to subscription and updates accordingly.
        """
        # Find subscription_payment for this invoice
        sp_stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.invoice_id == invoice_id
        )
        sp = (await db.execute(sp_stmt)).scalar_one_or_none()
        if sp is None:
            return  # Not a subscription invoice

        # Load subscription with row lock
        sub_stmt = (
            select(Subscription)
            .where(Subscription.id == sp.subscription_id)
            .with_for_update()
        )
        sub = (await db.execute(sub_stmt)).scalar_one_or_none()
        if sub is None:
            return

        # If past_due, recover to active
        if sub.status == SubscriptionStatus.past_due:
            sub.status = SubscriptionStatus.active
            logger.info(
                "Subscription recovered: %s past_due → active (invoice %s paid)",
                sub.id, invoice_id,
            )

        await db.flush()

    # ── Grace Period Check (called by renewer task) ──────────────────────

    async def check_grace_periods(self, db: AsyncSession) -> dict[str, int]:
        """Check all subscriptions for grace period violations.

        Returns dict with counts: {soft, hard, recovered}.
        """
        now = datetime.now(timezone.utc)
        counts = {"soft": 0, "hard": 0, "recovered": 0}

        # --- SOFT GRACE: active → past_due ---
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
        soft_subs = (await db.execute(soft_stmt)).scalars().all()
        for sub in soft_subs:
            sub.status = SubscriptionStatus.past_due
            counts["soft"] += 1
            logger.info("Subscription %s → past_due (soft grace exceeded)", sub.id)

        # --- HARD GRACE: past_due → expired ---
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
        hard_subs = (await db.execute(hard_stmt)).scalars().all()
        for sub in hard_subs:
            sub.status = SubscriptionStatus.expired
            counts["hard"] += 1
            logger.info("Subscription %s → expired (hard grace exceeded)", sub.id)

        # --- RECOVERY: past_due with paid invoice → active ---
        recovery_stmt = (
            select(Subscription)
            .join(SubscriptionPayment, SubscriptionPayment.subscription_id == Subscription.id)
            .join(Invoice, SubscriptionPayment.invoice_id == Invoice.id)
            .where(
                Subscription.status == SubscriptionStatus.past_due,
                Invoice.status.in_([
                    InvoiceStatus.paid,
                    InvoiceStatus.overpaid,
                    InvoiceStatus.late_paid,
                ]),
            )
            .group_by(Subscription.id)
        )
        recovery_subs = (await db.execute(recovery_stmt)).scalars().all()
        for sub in recovery_subs:
            sub.status = SubscriptionStatus.active
            counts["recovered"] += 1
            logger.info("Subscription %s → active (recovery from past_due)", sub.id)

        if any(counts.values()):
            await db.flush()

        return counts

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _get_for_update(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> Subscription:
        """Get subscription with row-level lock. Raises SubscriptionNotFoundError."""
        stmt = (
            select(Subscription)
            .where(
                Subscription.id == subscription_id,
                Subscription.merchant_id == merchant_id,
            )
            .with_for_update()
        )
        sub = (await db.execute(stmt)).scalar_one_or_none()
        if sub is None:
            raise SubscriptionNotFoundError(
                f"Subscription {subscription_id} not found."
            )
        return sub


# ─── Module-level instance ───────────────────────────────────────────────────

subscription_service = SubscriptionService()
