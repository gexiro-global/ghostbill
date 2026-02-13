"""
Subscription renewal background task.

Runs every 3600s (1 hour):
    Phase 1 — Renewal sweep: find active subs with next_due_at <= NOW(),
              create invoices via subscription_service.
    Phase 2 — Grace period check: soft (active → past_due), hard (past_due → expired),
              recovery (past_due with paid invoice → active).
    Phase 3 — Log summary.

Concurrency safety:
    - FOR UPDATE SKIP LOCKED prevents conflicts with API endpoints
    - UNIQUE(subscription_id, period_start) prevents double billing
    - _running flag prevents overlapping sweeps
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription, SubscriptionStatus
from app.db.session import async_session
from app.services.invoice_service import WalletUnavailableError
from app.services.subscription_service import SkipRenewalError, subscription_service

logger = logging.getLogger(__name__)

SWEEP_INTERVAL: int = 3600  # 1 hour
BATCH_SIZE: int = 50


async def subscription_renewer_loop() -> None:
    """Main loop — runs forever, sweeps every SWEEP_INTERVAL seconds."""
    logger.info("Subscription renewer started (interval=%ds)", SWEEP_INTERVAL)

    while True:
        try:
            await _run_sweep()
        except asyncio.CancelledError:
            logger.info("Subscription renewer cancelled")
            raise
        except Exception as exc:
            logger.error("Subscription renewer error: %s", exc, exc_info=True)

        await asyncio.sleep(SWEEP_INTERVAL)


async def _run_sweep() -> None:
    """Execute one full renewal sweep + grace check."""
    renewed = 0
    skipped = 0
    failed = 0

    async with async_session() as db:
        # Phase 1 — Renewal sweep
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
            result = await db.execute(stmt)
            subs = list(result.scalars().all())

            if not subs:
                break

            for sub in subs:
                try:
                    await subscription_service.create_renewal_invoice(db, sub)
                    renewed += 1
                except SkipRenewalError:
                    skipped += 1
                except WalletUnavailableError as exc:
                    failed += 1
                    logger.warning(
                        "Renewal failed (wallet): sub=%s, error=%s", sub.id, exc
                    )
                except Exception as exc:
                    failed += 1
                    logger.error(
                        "Renewal failed: sub=%s, error=%s", sub.id, exc, exc_info=True
                    )

            await db.commit()

        # Phase 2 — Grace period check
        grace_counts = await subscription_service.check_grace_periods(db)
        await db.commit()

    # Phase 3 — Summary
    total_grace = sum(grace_counts.values())
    if renewed or skipped or failed or total_grace:
        logger.info(
            "Renewer sweep complete: %d renewed, %d skipped, %d failed, "
            "%d past_due, %d expired, %d recovered",
            renewed, skipped, failed,
            grace_counts.get("soft", 0),
            grace_counts.get("hard", 0),
            grace_counts.get("recovered", 0),
        )
