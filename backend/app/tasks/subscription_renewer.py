"""Subscription renewal background task.

Runs every 3600s (1 hour):
    Phase 1 — Renewal sweep: find due subscriptions, create invoices
    Phase 2 — Grace period check: soft/hard/recovery
    Phase 3 — Log summary

Phase 6C: event logging for every renewal attempt.
Phase 8A: trial period expiration sweep.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Merchant, Subscription, SubscriptionStatus
from app.db.session import async_session
from app.services.invoice_service import WalletUnavailableError
from app.services.subscription_exceptions import SkipRenewalError
from app.services.subscription_renewal import (
    create_renewal_invoice,
    log_renewal_event,
)
from app.services.subscription_grace import check_grace_periods

logger = logging.getLogger(__name__)

SWEEP_INTERVAL: int = 3600
BATCH_SIZE: int = 50


async def subscription_renewer_loop() -> None:
    """Main loop — runs forever, sweeps every SWEEP_INTERVAL seconds."""
    logger.info("Subscription renewer started (interval=%ds)", SWEEP_INTERVAL)
    while True:
        try:
            await run_sweep()
        except asyncio.CancelledError:
            logger.info("Subscription renewer cancelled")
            raise
        except Exception as exc:
            logger.error("Subscription renewer error: %s", exc, exc_info=True)
        await asyncio.sleep(SWEEP_INTERVAL)


async def run_sweep() -> dict:
    """Execute one full renewal sweep + grace check.

    Returns summary dict.
    Phase 6C: logs events for wallet failures and DB errors.
    """
    renewed = 0
    skipped = 0
    failed = 0

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
                sub.status = SubscriptionStatus.active
                sub.next_due_at = datetime.now(timezone.utc)
                await db.flush()
                # Fire trial_ended event
                from app.services.webhook_service import webhook_service
                merchant = (await db.execute(
                    select(Merchant).where(Merchant.id == sub.merchant_id)
                )).scalar_one_or_none()
                if merchant:
                    await webhook_service.dispatch_subscription_event(
                        db=db, event_type="subscription.trial_ended",
                        subscription=sub, reason="trial_expired")
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
                try:
                    await create_renewal_invoice(db, sub)
                    renewed += 1
                    # success event logged inside _create_renewal_invoice
                except SkipRenewalError as exc:
                    skipped += 1
                    # Phase 6C: log skip event with result_type
                    await log_renewal_event(
                        db, sub.id, exc.result_type,
                        error_message=str(exc),
                    )
                except WalletUnavailableError as exc:
                    failed += 1
                    logger.warning("Renewal failed (wallet): sub=%s, %s", sub.id, exc)
                    # Phase 6C: log wallet failure
                    await log_renewal_event(
                        db, sub.id, "failed_wallet",
                        error_message=str(exc),
                    )
                except Exception as exc:
                    failed += 1
                    logger.error("Renewal failed: sub=%s, %s", sub.id, exc, exc_info=True)
                    # Phase 6C: log DB/other failure
                    await log_renewal_event(
                        db, sub.id, "failed_db",
                        error_message=str(exc),
                    )

            await db.commit()

        grace_counts = await check_grace_periods(db)
        # grace events logged inside check_grace_periods
        await db.commit()

    total_grace = sum(grace_counts.values())
    if renewed or skipped or failed or total_grace or trial_activated:
        logger.info(
            "Renewer: %d renewed, %d skipped, %d failed, %d trials_activated, %d past_due, %d expired, %d recovered",
            renewed, skipped, failed, trial_activated,
            grace_counts.get("soft", 0), grace_counts.get("hard", 0),
            grace_counts.get("recovered", 0),
        )

    return {"renewed": renewed, "skipped": skipped, "failed": failed, "trial_activated": trial_activated, "grace": grace_counts}
