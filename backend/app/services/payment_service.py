"""
Payment business logic — match, record, confirm, sum, reorg.

Responsibilities:
    - Match incoming TX to invoices via subaddr_index.minor → invoice_addresses.address_index
    - Record new payments (status=detected)
    - Update confirmations (detected → confirmed at threshold)
    - Handle reorgs (TX disappears → payment orphaned, invoice recalculated)
    - Sum cumulative payments per invoice and trigger status transitions
    - Dust filtering (ignore below DUST_THRESHOLD_ATOMIC)
    - Phase 5A: subscription payment hook (invoice.paid → subscription recovery)

CRITICAL:
    - amount_atomic (BIGINT, piconero) = source of truth
    - Idempotent: duplicate txid → update confirmations only
    - Invoice transitions delegated to invoice_service.update_status()
    - Multiple payments per invoice: SUM amount_atomic for cumulative total
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    AuditLog,
    Invoice,
    InvoiceAddress,
    InvoiceStatus,
    Payment,
    PaymentStatus,
)
from app.services.invoice_service import invoice_service
from app.services.monero_rpc import DUST_THRESHOLD_ATOMIC, atomic_to_xmr

logger = logging.getLogger(__name__)

CONFIRMATION_THRESHOLD: int = 10  # blocks required for "confirmed" status
REVERTIBLE_PAID_STATUSES: set[InvoiceStatus] = {
    InvoiceStatus.paid,
    InvoiceStatus.overpaid,
    InvoiceStatus.late_paid,
}
REVERTED_TARGET_STATUSES: set[InvoiceStatus] = {
    InvoiceStatus.pending,
    InvoiceStatus.partially_paid,
    InvoiceStatus.expired,
}


class PaymentError(Exception):
    """Base payment service error."""

    pass


class PaymentNotFoundError(PaymentError):
    """Payment not found."""

    pass


class PaymentService:
    """Payment business logic — stateless, operates on provided DB session."""

    async def find_invoice_by_subaddress_index(
        self,
        db: AsyncSession,
        account_index: int,
        address_index: int,
    ) -> Invoice | None:
        """Find invoice by subaddress index (account_index + address_index).

        Used by detection engine to match incoming TX to invoices.
        Returns Invoice with address and payments loaded, or None.
        """
        stmt = select(InvoiceAddress).where(
            InvoiceAddress.account_index == account_index,
            InvoiceAddress.address_index == address_index,
        )
        result = await db.execute(stmt)
        invoice_addr = result.scalar_one_or_none()

        if invoice_addr is None:
            return None

        # Load the invoice with relationships
        inv_stmt = (
            select(Invoice)
            .where(Invoice.id == invoice_addr.invoice_id)
            .options(
                selectinload(Invoice.address),
                selectinload(Invoice.payments),
            )
        )
        inv_result = await db.execute(inv_stmt)
        return inv_result.scalar_one_or_none()

    async def find_payment_by_tx_hash(
        self,
        db: AsyncSession,
        tx_hash: str,
    ) -> Payment | None:
        """Find existing payment by transaction hash."""
        stmt = select(Payment).where(Payment.tx_hash == tx_hash)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_payment(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        payment_id: uuid.UUID,
    ) -> Payment | None:
        """Get a single payment by ID, scoped to merchant via invoice."""
        stmt = (
            select(Payment)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .where(
                Payment.id == payment_id,
                Invoice.merchant_id == merchant_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_payments(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        invoice_id: uuid.UUID | None = None,
        status: PaymentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Payment], int]:
        """List payments for a merchant with optional filters.

        Returns:
            Tuple of (payments list, total count).
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        base_where = [Invoice.merchant_id == merchant_id]
        if invoice_id is not None:
            base_where.append(Payment.invoice_id == invoice_id)
        if status is not None:
            base_where.append(Payment.status == status)

        # Count
        count_stmt = select(func.count(Payment.id)).join(Invoice, Payment.invoice_id == Invoice.id).where(*base_where)
        total = (await db.execute(count_stmt)).scalar_one()

        # Data
        data_stmt = (
            select(Payment)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .where(*base_where)
            .order_by(Payment.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(data_stmt)
        payments = list(result.scalars().all())

        return payments, total

    async def process_transfer(
        self,
        db: AsyncSession,
        tx: dict,
        is_mempool: bool,
    ) -> Payment | None:
        """Process a single transfer from wallet-rpc get_transfers().

        This is the main entry point called by the detection engine.

        Flow:
            1. Extract subaddr_index.minor
            2. Lookup invoice by address_index
            3. Dust filter
            4. Check if payment already recorded (idempotent by tx_hash)
            5. If existing: update confirmations only
            6. If new: create payment + recalculate invoice status

        Args:
            tx: Transfer dict from wallet-rpc with keys:
                txid, amount, subaddr_index, confirmations, height, type
            is_mempool: True if TX is from mempool (pool key), False if confirmed (in key)

        Returns:
            Payment object if processed, None if skipped (dust, unknown address, etc.)
        """
        txid: str = tx["txid"]
        amount_atomic: int = int(tx["amount"])
        subaddr_index: dict = tx["subaddr_index"]
        account_index: int = subaddr_index["major"]
        address_index: int = subaddr_index["minor"]
        confirmations: int = int(tx.get("confirmations", 0))
        block_height: int | None = int(tx["height"]) if tx.get("height", 0) > 0 else None

        # 1. Dust filter
        if amount_atomic < DUST_THRESHOLD_ATOMIC:
            logger.debug(
                "Dust payment ignored: txid=%s, amount=%d atomic",
                txid[:16],
                amount_atomic,
            )
            return None

        # 2. Find invoice by subaddress index
        invoice = await self.find_invoice_by_subaddress_index(db, account_index, address_index)
        if invoice is None:
            # Unknown subaddress — not our invoice (index 0 = primary address, etc.)
            return None

        # 3. Check for existing payment (idempotent)
        existing = await self.find_payment_by_tx_hash(db, txid)
        if existing:
            transitioned = await self._update_confirmations(db, existing, confirmations, block_height)
            # Re-evaluate invoice status after confirmation update
            if invoice.status != InvoiceStatus.cancelled and (
                transitioned or existing.status == PaymentStatus.confirmed
            ):
                await self._recalculate_invoice_status(db, invoice)
            return existing

        # 4. Create new payment. Cancelled invoices record payment but never settle.
        payment = await self._create_payment(
            db=db,
            invoice=invoice,
            txid=txid,
            amount_atomic=amount_atomic,
            confirmations=confirmations,
            block_height=block_height,
            is_mempool=is_mempool,
        )

        # 5. Recalculate invoice status unless cancelled (DEC-01 exception path).
        if invoice.status != InvoiceStatus.cancelled:
            await self._recalculate_invoice_status(db, invoice)

        return payment

    async def _create_payment(
        self,
        db: AsyncSession,
        invoice: Invoice,
        txid: str,
        amount_atomic: int,
        confirmations: int,
        block_height: int | None,
        is_mempool: bool,
    ) -> Payment:
        """Record a new payment in the database."""
        # Determine initial status
        if confirmations >= CONFIRMATION_THRESHOLD:
            status = PaymentStatus.confirmed
            confirmed_at = datetime.now(timezone.utc)
        else:
            status = PaymentStatus.detected
            confirmed_at = None

        amount_xmr = atomic_to_xmr(amount_atomic)

        payment = Payment(
            invoice_id=invoice.id,
            tx_hash=txid,
            amount_atomic=amount_atomic,
            amount_xmr=amount_xmr,
            status=status,
            confirmations=confirmations,
            block_height=block_height,
            confirmed_at=confirmed_at,
        )
        db.add(payment)

        audit_details = {
            "invoice_id": str(invoice.id),
            "tx_hash": txid,
            "amount_atomic": amount_atomic,
            "confirmations": confirmations,
            "is_mempool": is_mempool,
        }
        if invoice.status == InvoiceStatus.cancelled:
            audit_details["metadata"] = {"exception": "cancelled_invoice_payment"}

        # Audit log
        audit = AuditLog(
            merchant_id=invoice.merchant_id,
            action="payment.detected",
            entity_type="payment",
            entity_id=payment.id,
            details=audit_details,
        )
        db.add(audit)

        await db.flush()

        logger.info(
            "Payment recorded: tx=%s, invoice=%s, amount=%d atomic, status=%s",
            txid[:16],
            invoice.id,
            amount_atomic,
            status.value,
        )

        return payment

    async def _update_confirmations(
        self,
        db: AsyncSession,
        payment: Payment,
        confirmations: int,
        block_height: int | None,
    ) -> bool:
        """Update confirmation count for an existing payment.

        Returns True if payment transitioned to confirmed status.
        """
        if payment.status == PaymentStatus.orphaned:
            # Orphaned payments are not updated
            return False

        changed = False

        # Update confirmations count
        if confirmations > payment.confirmations:
            payment.confirmations = confirmations
            changed = True

        # Update block height if not set
        if block_height is not None and payment.block_height is None:
            payment.block_height = block_height
            changed = True

        # Check threshold transition: detected → confirmed
        if payment.status == PaymentStatus.detected and confirmations >= CONFIRMATION_THRESHOLD:
            payment.status = PaymentStatus.confirmed
            payment.confirmed_at = datetime.now(timezone.utc)
            changed = True

            invoice_stmt = select(Invoice).where(Invoice.id == payment.invoice_id)
            invoice = (await db.execute(invoice_stmt)).scalar_one_or_none()

            # Audit log
            audit = AuditLog(
                merchant_id=invoice.merchant_id if invoice is not None else None,
                action="payment.confirmed",
                entity_type="payment",
                entity_id=payment.id,
                details={
                    "tx_hash": payment.tx_hash,
                    "confirmations": confirmations,
                    "invoice_id": str(payment.invoice_id),
                },
            )
            db.add(audit)

            logger.info(
                "Payment confirmed: tx=%s, confirmations=%d",
                payment.tx_hash[:16],
                confirmations,
            )

        if changed:
            await db.flush()

        return payment.status == PaymentStatus.confirmed and changed

    async def _recalculate_invoice_status(
        self,
        db: AsyncSession,
        invoice: Invoice,
    ) -> InvoiceStatus:
        """Recalculate invoice status based on cumulative payments.

        Logic:
            - Sum confirmed payments only
            - Compare cumulative total to invoice.amount_atomic
            - Determine new status:
                confirmed total > amount → overpaid
                confirmed total >= amount → paid
                0 < confirmed total < amount → partially_paid
                confirmed total == 0 → pending
                expired + confirmed total >= amount → late_paid
                expired + confirmed total < amount → expired
            - Delegate transition to invoice_service.update_status()

        Returns:
            Current invoice status after recalculation.
        """
        # Refresh invoice to get latest status
        await db.refresh(invoice)

        # Cancelled invoices never settle automatically (DEC-01).
        if invoice.status == InvoiceStatus.cancelled:
            return invoice.status

        # Sum confirmed payments only. Detected payments are recorded but do not settle invoices.
        cumulative = await self.sum_invoice_payments(db, invoice.id)
        required = invoice.amount_atomic

        # Track old status for subscription hook
        old_status = invoice.status

        # Determine target status
        new_status: InvoiceStatus | None = None

        if invoice.status == InvoiceStatus.expired:
            if cumulative >= required:
                new_status = InvoiceStatus.late_paid
            else:
                new_status = InvoiceStatus.expired

        elif invoice.status == InvoiceStatus.late_paid:
            if cumulative >= required:
                new_status = InvoiceStatus.late_paid
            else:
                new_status = InvoiceStatus.expired

        else:
            if cumulative > required:
                new_status = InvoiceStatus.overpaid
            elif cumulative >= required:
                new_status = InvoiceStatus.paid
            elif cumulative > 0:
                new_status = InvoiceStatus.partially_paid
            else:
                new_status = InvoiceStatus.pending

        # Apply transition
        if new_status is not None and invoice.status != new_status:
            details = {
                "cumulative_atomic": cumulative,
                "required_atomic": required,
            }
            if invoice_service.can_transition(invoice.status, new_status):
                await invoice_service.update_status(db, invoice, new_status, details=details)
            elif invoice.status == InvoiceStatus.pending and new_status == InvoiceStatus.overpaid:
                await invoice_service.update_status(db, invoice, InvoiceStatus.paid, details=details)
                await invoice_service.update_status(db, invoice, InvoiceStatus.overpaid, details=details)

        # === Phase 5A: Subscription payment hook ===
        # If invoice newly transitioned to a paid state, notify subscription service.
        paid_statuses = {
            InvoiceStatus.paid,
            InvoiceStatus.overpaid,
            InvoiceStatus.late_paid,
        }
        if invoice.status in paid_statuses and old_status not in paid_statuses and old_status != invoice.status:
            try:
                from app.services.subscription_grace import handle_subscription_payment

                await handle_subscription_payment(db, invoice.id)
            except Exception as exc:
                logger.warning(
                    "Subscription payment hook failed for invoice %s: %s",
                    invoice.id,
                    exc,
                )
        # === END Phase 5A ===

        return invoice.status

    async def sum_invoice_payments(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
    ) -> int:
        """Sum amount_atomic of confirmed payments for an invoice.

        Detected payments are recorded and webhooks fire, but settlement is confirmed-only.
        """
        stmt = select(func.coalesce(func.sum(Payment.amount_atomic), 0)).where(
            Payment.invoice_id == invoice_id,
            Payment.status == PaymentStatus.confirmed,
        )
        result = await db.execute(stmt)
        return int(result.scalar_one())

    async def sum_detected_payments(
        self,
        db: AsyncSession,
        invoice_id: uuid.UUID,
    ) -> int:
        """Sum amount_atomic of detected payments for observability and tests."""
        stmt = select(func.coalesce(func.sum(Payment.amount_atomic), 0)).where(
            Payment.invoice_id == invoice_id,
            Payment.status == PaymentStatus.detected,
        )
        result = await db.execute(stmt)
        return int(result.scalar_one())

    async def handle_reorg(
        self,
        db: AsyncSession,
        payment: Payment,
    ) -> None:
        """Mark a payment as orphaned due to blockchain reorg.

        Called when a previously seen TX disappears from wallet-rpc.

        Flow:
            1. Mark payment as orphaned
            2. Load the invoice
            3. Recalculate invoice status based on remaining payments
        """
        if payment.status == PaymentStatus.orphaned:
            return  # Already orphaned

        old_status = payment.status
        payment.status = PaymentStatus.orphaned

        invoice_stmt = select(Invoice).where(Invoice.id == payment.invoice_id)
        invoice = (await db.execute(invoice_stmt)).scalar_one_or_none()

        # Audit log
        audit = AuditLog(
            merchant_id=invoice.merchant_id if invoice is not None else None,
            action="payment.orphaned",
            entity_type="payment",
            entity_id=payment.id,
            details={
                "tx_hash": payment.tx_hash,
                "previous_status": old_status.value,
                "invoice_id": str(payment.invoice_id),
            },
        )
        db.add(audit)

        await db.flush()

        logger.warning(
            "Payment orphaned (reorg): tx=%s, invoice=%s",
            payment.tx_hash[:16],
            payment.invoice_id,
        )

        # Recalculate invoice status with remaining non-orphaned payments
        if invoice is not None:
            await self._recalculate_invoice_status(db, invoice)

    async def get_unconfirmed_payments(
        self,
        db: AsyncSession,
    ) -> list[Payment]:
        """Get all payments with status=detected (need confirmation tracking).

        Used by detection engine to poll wallet-rpc for updated confirmations.
        """
        stmt = select(Payment).where(Payment.status == PaymentStatus.detected).order_by(Payment.detected_at.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def determine_webhook_events(
        payment: Payment,
        invoice: Invoice,
        old_invoice_status: InvoiceStatus,
        old_payment_status: PaymentStatus | None,
    ) -> list[str]:
        """Determine which webhook events should fire.

        Called after processing a transfer to decide which events to dispatch.

        Returns:
            List of event type strings (e.g. ["payment.detected", "invoice.paid"])
        """
        events: list[str] = []

        # Payment events
        if old_payment_status is None:
            # New payment
            events.append("payment.detected")
        elif old_payment_status == PaymentStatus.detected and payment.status == PaymentStatus.confirmed:
            events.append("payment.confirmed")
        elif payment.status == PaymentStatus.orphaned:
            events.append("payment.orphaned")

        if old_payment_status is None and old_invoice_status == InvoiceStatus.cancelled:
            events.append("invoice.exception_payment")

        if old_invoice_status in REVERTIBLE_PAID_STATUSES and invoice.status in REVERTED_TARGET_STATUSES:
            events.append("invoice.reverted")
            return events

        # Invoice status change events
        if invoice.status != old_invoice_status:
            status_event_map: dict[InvoiceStatus, str] = {
                InvoiceStatus.paid: "invoice.paid",
                InvoiceStatus.partially_paid: "invoice.partially_paid",
                InvoiceStatus.overpaid: "invoice.overpaid",
                InvoiceStatus.late_paid: "invoice.late_paid",
                InvoiceStatus.expired: "invoice.expired",
            }
            event = status_event_map.get(invoice.status)
            if event:
                events.append(event)

        return events


payment_service = PaymentService()
