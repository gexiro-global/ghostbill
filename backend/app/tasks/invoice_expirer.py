"""
Background task: expire pending invoices every 60 seconds.

Started in FastAPI lifespan alongside price_updater.
Uses its own DB session per cycle (independent of request sessions).
"""

import asyncio
import logging

from app.db.session import async_session
from app.services.expiration_service import expiration_service
from app.tasks.detection_helpers import acquire_task_lease

logger = logging.getLogger(__name__)

EXPIRATION_INTERVAL: int = 60  # seconds
LEASE_TTL_SECONDS: int = EXPIRATION_INTERVAL * 2


async def run_invoice_expirer() -> None:
    """Long-running loop: expire pending invoices every 60 seconds.

    Each cycle:
        1. Open a fresh DB session
        2. Call expiration_service.expire_pending_invoices()
        3. Commit on success, rollback on error
        4. Sleep 60 seconds

    Errors are logged but never crash the loop.
    """
    logger.info("Invoice expirer started (interval=%ds)", EXPIRATION_INTERVAL)

    while True:
        try:
            if not await acquire_task_lease("invoice_expirer", LEASE_TTL_SECONDS):
                await asyncio.sleep(EXPIRATION_INTERVAL)
                continue

            async with async_session() as db:
                async with db.begin():
                    expired_ids = await expiration_service.expire_pending_invoices(db)

                if expired_ids:
                    logger.debug("Expiration cycle: %d invoice(s) expired", len(expired_ids))

        except asyncio.CancelledError:
            logger.info("Invoice expirer stopped")
            raise

        except Exception:
            logger.exception("Invoice expirer cycle error")

        await asyncio.sleep(EXPIRATION_INTERVAL)
