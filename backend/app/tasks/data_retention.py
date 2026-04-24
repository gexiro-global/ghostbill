"""
Data retention background task.

Runs every hour, cleans up old data per retention policy:
- Expired/cancelled invoices: 48 hours after expiry/cancellation
- Webhook delivery logs: 30 days
- Audit log entries: 90 days
- Payments: NEVER deleted (blockchain record, legal compliance)

Deletes are batched (LIMIT 500 per cycle) to avoid long-running transactions.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session

logger = logging.getLogger(__name__)

# Retention periods
INVOICE_RETENTION_HOURS = 48  # Expired/cancelled invoices
WEBHOOK_RETENTION_DAYS = 30  # Webhook delivery logs
AUDIT_RETENTION_DAYS = 90  # Audit log entries
BATCH_SIZE = 500  # Max rows per DELETE
CYCLE_INTERVAL_SECONDS = 3600  # Run every hour


async def _cleanup_expired_invoices(db: AsyncSession) -> int:
    """Delete expired/cancelled invoices older than retention period.

    Only deletes invoices in terminal states (expired, cancelled).
    Related invoice_addresses are cascade-deleted by FK.
    Invoices with payments are NOT deleted (payments NEVER deleted).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=INVOICE_RETENTION_HOURS)

    result = await db.execute(
        text("""
            DELETE FROM invoices
            WHERE id IN (
                SELECT i.id FROM invoices i
                LEFT JOIN payments p ON p.invoice_id = i.id
                WHERE i.status IN ('expired', 'cancelled')
                AND i.updated_at < :cutoff
                AND p.id IS NULL
                LIMIT :batch_size
            )
        """),
        {"cutoff": cutoff, "batch_size": BATCH_SIZE},
    )
    return result.rowcount or 0


async def _cleanup_webhook_logs(db: AsyncSession) -> int:
    """Delete webhook delivery logs older than retention period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=WEBHOOK_RETENTION_DAYS)

    result = await db.execute(
        text("""
            DELETE FROM webhook_deliveries
            WHERE id IN (
                SELECT id FROM webhook_deliveries
                WHERE created_at < :cutoff
                LIMIT :batch_size
            )
        """),
        {"cutoff": cutoff, "batch_size": BATCH_SIZE},
    )
    return result.rowcount or 0


async def _cleanup_audit_logs(db: AsyncSession) -> int:
    """Delete audit log entries older than retention period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=AUDIT_RETENTION_DAYS)

    result = await db.execute(
        text("""
            DELETE FROM audit_log
            WHERE id IN (
                SELECT id FROM audit_log
                WHERE created_at < :cutoff
                LIMIT :batch_size
            )
        """),
        {"cutoff": cutoff, "batch_size": BATCH_SIZE},
    )
    return result.rowcount or 0


async def run_retention_cleanup() -> None:
    """Execute one retention cleanup cycle."""
    async with async_session() as db:
        try:
            invoices_deleted = await _cleanup_expired_invoices(db)
            webhooks_deleted = await _cleanup_webhook_logs(db)
            audit_deleted = await _cleanup_audit_logs(db)
            await db.commit()

            total = invoices_deleted + webhooks_deleted + audit_deleted
            if total > 0:
                logger.info(
                    "Retention cleanup: invoices=%d, webhooks=%d, audit=%d",
                    invoices_deleted,
                    webhooks_deleted,
                    audit_deleted,
                )
            else:
                logger.debug("Retention cleanup: nothing to delete")

        except Exception as e:
            logger.error("Retention cleanup failed: %s", e)
            try:
                await db.rollback()
            except Exception:
                pass


async def data_retention_loop() -> None:
    """Background loop running retention cleanup every hour."""
    logger.info(
        "Data retention task started (invoices=%dh, webhooks=%dd, audit=%dd)",
        INVOICE_RETENTION_HOURS,
        WEBHOOK_RETENTION_DAYS,
        AUDIT_RETENTION_DAYS,
    )

    # Wait 5 minutes after startup before first cleanup
    await asyncio.sleep(300)

    while True:
        try:
            await run_retention_cleanup()
        except asyncio.CancelledError:
            logger.info("Data retention task cancelled")
            raise
        except Exception as e:
            logger.error("Data retention loop error: %s", e)

        await asyncio.sleep(CYCLE_INTERVAL_SECONDS)
