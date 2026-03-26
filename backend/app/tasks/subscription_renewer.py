"""Subscription renewal background task.

Runs every 3600s (1 hour):
    Phase 1 — Renewal sweep: find due subscriptions, create invoices
    Phase 2 — Grace period check: soft/hard/recovery
    Phase 3 — Log summary
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription, SubscriptionStatus
from app.db.session import async_session
from app.services.invoice_service import WalletUnavailableError
from app.services.subscription_exceptions import SkipRenewalError
from app.services.subscription_renewal import create_renewal_invoice
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
    """Execute one full renewal sweep + grace check. Returns summary dict."""
    renewed = 0
    skipped = 0
    failed = 0

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
                except SkipRenewalError:
                    skipped += 1
                except WalletUnavailableError as exc:
                    failed += 1
                    logger.warning("Renewal failed (wallet): sub=%s, %s", sub.id, exc)
                except Exception as exc:
                    failed += 1
                    logger.error("Renewal failed: sub=%s, %s", sub.id, exc, exc_info=True)

            await db.commit()

        grace_counts = await check_grace_periods(db)
        await db.commit()

    total_grace = sum(grace_counts.values())
    if renewed or skipped or failed or total_grace:
        logger.info(
            "Renewer: %d renewed, %d skipped, %d failed, %d past_due, %d expired, %d recovered",
            renewed, skipped, failed,
            grace_counts.get("soft", 0), grace_counts.get("hard", 0),
            grace_counts.get("recovered", 0),
        )

    return {"renewed": renewed, "skipped": skipped, "failed": failed, "grace": grace_counts}
