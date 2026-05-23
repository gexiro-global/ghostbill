"""Subscription renewal background task.

Runs every 3600s (1 hour):
    Phase 1 — Renewal sweep: find due subscriptions, create invoices
    Phase 2 — Grace period check: soft/hard/recovery
    Phase 3 — Log summary

Phase 6C: event logging for every renewal attempt.
Phase 8A: trial period expiration sweep.
Phase 8B: prepay invoice guard (skip if pending, clear if expired).
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Invoice,
    InvoiceStatus,
    Merchant,
    Subscription,
    SubscriptionStatus,
)
from app.db.session import async_session
from app.services.invoice_service import WalletUnavailableError
from app.services.subscription_exceptions import SkipRenewalError, transition_subscription_status
from app.services.subscription_grace import check_grace_periods
from app.services.subscription_renewal import (
    create_renewal_invoice,
    log_renewal_event,
)
from app.tasks.detection_helpers import acquire_task_lease

logger = logging.getLogger(__name__)

SWEEP_INTERVAL: int = 3600
BATCH_SIZE: int = 50
LEASE_TTL_SECONDS: int = SWEEP_INTERVAL * 2


async def subscription_renewer_loop() -> None:
    """Main loop — runs forever, sweeps every SWEEP_INTERVAL seconds."""
    logger.info("Subscription renewer started (interval=%ds)", SWEEP_INTERVAL)
    while True:
        try:
            if await acquire_task_lease("subscription_renewer", LEASE_TTL_SECONDS):
                await run_sweep()
        except asyncio.CancelledError:
            logger.info("Subscription renewer cancelled")
            raise
        except Exception as exc:
            logger.error("Subscription renewer error: %s", exc, exc_info=True)
        await asyncio.sleep(SWEEP_INTERVAL)


async def _check_prepay_guard(db: AsyncSession, sub: Subscription) -> bool:
    """Phase 8B: Check prepay invoice status.

    Returns True if renewal should be SKIPPED (prepay active).
    Returns False if prepay cleared and renewal can proceed.
    """
    if sub.prepay_invoice_id is None:
        return False

    inv_stmt = select(Invoice).where(Invoice.id == sub.prepay_invoice_id)
    invoice = (await db.execute(inv_stmt)).scalar_one_or_none()

    if invoice is None:
        # Orphaned reference — clear and proceed
        sub.prepay_invoice_id = None
        sub.prepaid_until = None
        await db.flush()
        logger.warning("Cleared orphaned prepay_invoice_id for sub %s", sub.id)
        return False

    if invoice.status == InvoiceStatus.pending:
        # Prepay invoice still pending — skip renewal
        return True

    if invoice.status in (
        InvoiceStatus.paid,
        InvoiceStatus.overpaid,
        InvoiceStatus.late_paid,
    ):
        # Prepay already paid — next_due_at should be advanced. Skip.
        return True

    # Invoice expired or cancelled — clear prepay and allow renewal
    from app.services.subscription_prepay import clear_expired_prepay

    await clear_expired_prepay(db, sub)
    await log_renewal_event(
        db,
        sub.id,
        "prepay_expired",
        details={"invoice_id": str(invoice.id), "invoice_status": invoice.status.value},
    )
    return False


async def run_sweep() -> dict:
    """Execute one full renewal sweep + grace check.

    Returns summary dict.
    Phase 6C: logs events for wallet failures and DB errors.
    """
    renewed = 0
    skipped = 0
    failed = 0
    prepay_skipped = 0

    # Phase 8A: Trial expiration sweep
    trial_activated = 0
    async with async_session() as db:
        trial_stmt = (
            select(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.trialing,
                Subscription.trial_end_at <= datetime.now(timezone.utc),
            )
            .with_for_update(skip_locked=True)
            .limit(BATCH_SIZE)
        )
        trial_subs = list((await db.execute(trial_stmt)).scalars().all())
        for sub in trial_subs:
            try:
                transition_subscription_status(sub, SubscriptionStatus.active)
                sub.next_due_at = datetime.now(timezone.utc)
                await db.flush()
                # Fire trial_ended event
                from app.services.webhook_service import webhook_service

                merchant = (
                    await db.execute(select(Merchant).where(Merchant.id == sub.merchant_id))
                ).scalar_one_or_none()
                if merchant:
                    await webhook_service.dispatch_subscription_event(
                        db=db, event_type="subscription.trial_ended", subscription=sub, reason="trial_expired"
                    )
                # Create first invoice
                try:
                    await create_renewal_invoice(db, sub)
                except (SkipRenewalError, WalletUnavailableError) as exc:
                    logger.warning("First invoice after trial failed: sub=%s, %s", sub.id, exc)
                trial_activated += 1
                logger.info("Trial ended, activated: sub=%s", sub.id)
            except Exception as exc:
                logger.error("Trial activation failed: sub=%s, %s", sub.id, exc, exc_info=True)
        if trial_subs:
            await db.commit()

    async with async_session() as db:
        while True:
            stmt = (
                select(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.active,
                    Subscription.next_due_at <= datetime.now(timezone.utc),
                )
                .with_for_update(skip_locked=True)
                .limit(BATCH_SIZE)
            )
            subs = list((await db.execute(stmt)).scalars().all())
            if not subs:
                break

            for sub in subs:
                # Phase 8B: check prepay guard
                if await _check_prepay_guard(db, sub):
                    prepay_skipped += 1
                    continue

                try:
                    await create_renewal_invoice(db, sub)
                    renewed += 1
                except SkipRenewalError as exc:
                    skipped += 1
                    await log_renewal_event(
                        db,
                        sub.id,
                        exc.result_type,
                        error_message=str(exc),
                    )
                except WalletUnavailableError as exc:
                    failed += 1
                    logger.warning("Renewal failed (wallet): sub=%s, %s", sub.id, exc)
                    await log_renewal_event(
                        db,
                        sub.id,
                        "failed_wallet",
                        error_message=str(exc),
                    )
                except Exception as exc:
                    failed += 1
                    logger.error("Renewal failed: sub=%s, %s", sub.id, exc, exc_info=True)
                    await log_renewal_event(
                        db,
                        sub.id,
                        "failed_db",
                        error_message=str(exc),
                    )

            await db.commit()

        grace_counts = await check_grace_periods(db)
        await db.commit()

    total_grace = sum(grace_counts.values())
    if renewed or skipped or failed or total_grace or trial_activated or prepay_skipped:
        logger.info(
            "Renewer: %d renewed, %d skipped, %d failed, %d trials, %d prepay_skipped, "
            "%d past_due, %d expired, %d recovered",
            renewed,
            skipped,
            failed,
            trial_activated,
            prepay_skipped,
            grace_counts.get("soft", 0),
            grace_counts.get("hard", 0),
            grace_counts.get("recovered", 0),
        )

    return {
        "renewed": renewed,
        "skipped": skipped,
        "failed": failed,
        "trial_activated": trial_activated,
        "prepay_skipped": prepay_skipped,
        "grace": grace_counts,
    }
