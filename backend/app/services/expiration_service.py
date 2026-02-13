"""
Invoice expiration service — batch-expire pending invoices.

Called by background task (invoice_expirer.py) every 60 seconds.

Race condition protection:
    NOT EXISTS (payments with detected/confirmed) ensures that if the
    detection engine processes a payment in the same second as expiry,
    the invoice won't be incorrectly expired.

    - Detection runs first → marks paid → expiration skips (NOT EXISTS)
    - Expiration runs first → marks expired → detection finds expired → marks late_paid

No webhook dispatched for expired invoices (merchant can poll or check dashboard).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
)

logger = logging.getLogger(__name__)


class ExpirationService:
    """Batch-expire pending invoices past their expires_at timestamp."""

    async def expire_pending_invoices(self, db: AsyncSession) -> list[str]:
        """Find and expire all pending invoices that are past due.

        Uses a single UPDATE ... WHERE query with NOT EXISTS subquery
        for atomicity and race condition safety.

        Returns:
            List of expired invoice ID strings (for logging).
        """
        now = datetime.now(timezone.utc)

        # Subquery: invoice has at least one detected or confirmed payment
        has_active_payment = (
            exists()
            .where(
                and_(
                    Payment.invoice_id == Invoice.id,
                    Payment.status.in_([
                        PaymentStatus.detected,
                        PaymentStatus.confirmed,
                    ]),
                )
            )
        )

        # Batch UPDATE with RETURNING
        stmt = (
            update(Invoice)
            .where(
                Invoice.status == InvoiceStatus.pending,
                Invoice.expires_at < now,
                ~has_active_payment,
            )
            .values(
                status=InvoiceStatus.expired,
                updated_at=now,
            )
            .returning(Invoice.id, Invoice.merchant_id)
        )

        result = await db.execute(stmt)
        expired_rows = result.all()

        if not expired_rows:
            return []

        # Create audit log entries for each expired invoice
        for invoice_id, merchant_id in expired_rows:
            audit = AuditLog(
                merchant_id=merchant_id,
                action="invoice.expired",
                entity_type="invoice",
                entity_id=invoice_id,
                details={"expired_at": now.isoformat()},
            )
            db.add(audit)

        await db.flush()

        expired_ids = [str(row[0]) for row in expired_rows]

        logger.info(
            "Expired %d pending invoice(s): %s",
            len(expired_ids),
            ", ".join(expired_ids[:10]),  # Log max 10 IDs
        )

        return expired_ids


# ─── Module-level instance ───────────────────────────────────────────────────

expiration_service = ExpirationService()
