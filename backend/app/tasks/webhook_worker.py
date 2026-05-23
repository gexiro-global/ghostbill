"""
Webhook worker — background task processing pending deliveries.

Runs every 10 seconds:
    1. Fetch pending deliveries where next_retry_at <= NOW()
    2. For each: load merchant → attempt delivery → update result
    3. Handles graceful shutdown via CancelledError

CRITICAL:
    - Own DB session per cycle (no shared state)
    - Merchant webhook_secret loaded per delivery (not cached)
    - Random jitter per delivery (metadata protection)
    - CancelledError for clean shutdown
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.models import Merchant
from app.db.session import async_session
from app.services.webhook_service import webhook_service
from app.tasks.detection_helpers import acquire_task_lease

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

WORKER_INTERVAL: int = 10  # seconds between cycles
BATCH_SIZE: int = 50  # max deliveries per cycle
LEASE_TTL_SECONDS: int = WORKER_INTERVAL * 2


# ─── Background Task ────────────────────────────────────────────────────────


async def webhook_worker_loop() -> None:
    """Background loop: process pending webhook deliveries.

    Runs indefinitely until cancelled. Each cycle:
        1. Opens a fresh DB session
        2. Fetches pending deliveries ready for (re)delivery
        3. Attempts each delivery with HMAC-signed HTTP POST
        4. Updates delivery status (delivered/retry/failed)
        5. Commits and sleeps
    """
    logger.info("Webhook worker started, processing every %ds", WORKER_INTERVAL)

    while True:
        try:
            if not await acquire_task_lease("webhook_worker", LEASE_TTL_SECONDS):
                await asyncio.sleep(WORKER_INTERVAL)
                continue

            processed = 0

            async with async_session() as db:
                # Claim pending deliveries with SELECT FOR UPDATE SKIP LOCKED.
                deliveries = await webhook_service.claim_pending_deliveries(db, limit=BATCH_SIZE)

                if not deliveries:
                    await asyncio.sleep(WORKER_INTERVAL)
                    continue

                for delivery in deliveries:
                    try:
                        # Load merchant for webhook_secret
                        merchant_stmt = select(Merchant).where(Merchant.id == delivery.merchant_id)
                        merchant_result = await db.execute(merchant_stmt)
                        merchant = merchant_result.scalar_one_or_none()

                        if merchant is None or not merchant.webhook_secret:
                            reason = "merchant_not_found" if merchant is None else "webhook_secret_missing"
                            logger.warning(
                                "Webhook delivery %s: %s, moving to DLQ",
                                delivery.id,
                                reason,
                            )
                            await webhook_service._move_to_dlq(db, delivery, failure_reason=reason)
                            continue

                        # Attempt delivery
                        success = await webhook_service.attempt_delivery(delivery, merchant.webhook_secret)

                        # Process result (update status, schedule retry if needed)
                        await webhook_service.process_delivery_result(db, delivery, success)
                        if success:
                            await webhook_service.mark_dlq_resolved_for_delivery(db, delivery)

                        processed += 1

                    except Exception:
                        logger.exception("Error processing webhook delivery %s", delivery.id)

                await db.commit()

            if processed > 0:
                logger.info("Webhook worker: processed %d deliveries", processed)

        except asyncio.CancelledError:
            logger.info("Webhook worker shutting down")
            raise

        except Exception:
            logger.exception("Webhook worker cycle error")

        await asyncio.sleep(WORKER_INTERVAL)
