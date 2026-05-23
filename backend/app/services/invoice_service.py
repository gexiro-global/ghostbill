"""
Invoice business logic — create, cancel, get, list, state machine.

State machine (7 statuses):
    pending → paid, partially_paid, expired, cancelled
    partially_paid → paid, overpaid, pending
    expired → late_paid
    paid → overpaid, partially_paid, pending
    overpaid → paid, partially_paid, pending
    late_paid → expired
    cancelled → (terminal, no transitions)

CRITICAL:
    - amount_atomic (BIGINT, piconero) = source of truth
    - fiat_rate snapshot at creation time
    - wallet-rpc may be unavailable (monerod syncing) → graceful error
    - Cancel: only pending invoices with zero payments
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditLog,
    Invoice,
    InvoiceAddress,
    InvoiceStatus,
    Merchant,
    Payment,
    PaymentStatus,
)
from app.services.monero_rpc import (
    MoneroRPCConnectionError,
    MoneroRPCError,
    get_monero_rpc,
    xmr_to_atomic,
)

logger = logging.getLogger(__name__)

EXPIRES_IN_MIN: int = 600  # 10 minutes
EXPIRES_IN_MAX: int = 2592000  # 30 days (subscription grace periods)
EXPIRES_IN_DEFAULT: int = 3600  # 1 hour

VALID_TRANSITIONS: dict[InvoiceStatus, list[InvoiceStatus]] = {
    InvoiceStatus.pending: [
        InvoiceStatus.paid,
        InvoiceStatus.partially_paid,
        InvoiceStatus.expired,
        InvoiceStatus.cancelled,
    ],
    InvoiceStatus.partially_paid: [
        InvoiceStatus.paid,
        InvoiceStatus.overpaid,
        InvoiceStatus.pending,
    ],
    InvoiceStatus.expired: [
        InvoiceStatus.late_paid,
    ],
    InvoiceStatus.paid: [
        InvoiceStatus.overpaid,
        InvoiceStatus.partially_paid,
        InvoiceStatus.pending,
    ],
    InvoiceStatus.overpaid: [
        InvoiceStatus.paid,
        InvoiceStatus.partially_paid,
        InvoiceStatus.pending,
    ],
    InvoiceStatus.late_paid: [
        InvoiceStatus.expired,
    ],
    # Truly terminal state — cancelled invoices never settle automatically.
    InvoiceStatus.cancelled: [],
}

TERMINAL_STATUSES: set[InvoiceStatus] = {
    InvoiceStatus.cancelled,
}


class InvoiceError(Exception):
    """Base invoice service error."""

    pass


class InvoiceNotFoundError(InvoiceError):
    """Invoice does not exist or does not belong to merchant."""

    pass


class InvoiceValidationError(InvoiceError):
    """Input validation failed."""

    pass


class InvoiceStateError(InvoiceError):
    """Invalid state transition attempted."""

    pass


class WalletUnavailableError(InvoiceError):
    """wallet-rpc is not reachable (monerod syncing, container down, etc.)."""

    pass


class InvoiceService:
    """Invoice business logic — stateless, operates on provided DB session."""

    @staticmethod
    def _parse_amount_xmr(raw: str | float | Decimal) -> Decimal:
        """Parse and validate XMR amount.

        Accepts string, float, or Decimal. Returns Decimal.
        Raises InvoiceValidationError if invalid or non-positive.
        """
        try:
            amount = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            raise InvoiceValidationError(f"Invalid amount_xmr: {raw!r}. Must be a positive decimal number.")

        if amount <= 0:
            raise InvoiceValidationError("amount_xmr must be greater than 0.")

        # Sanity cap: 1 billion XMR (total supply ~18.4M)
        if amount > Decimal("1000000000"):
            raise InvoiceValidationError("amount_xmr exceeds maximum allowed value.")

        return amount

    @staticmethod
    def _validate_expires_in(expires_in: int | None) -> int:
        """Validate and return expires_in seconds."""
        if expires_in is None:
            return EXPIRES_IN_DEFAULT

        if not isinstance(expires_in, int) or expires_in < EXPIRES_IN_MIN or expires_in > EXPIRES_IN_MAX:
            raise InvoiceValidationError(f"expires_in must be between {EXPIRES_IN_MIN} and {EXPIRES_IN_MAX} seconds.")
        return expires_in

    @staticmethod
    def can_transition(current: InvoiceStatus, target: InvoiceStatus) -> bool:
        """Check if a state transition is valid."""
        return target in VALID_TRANSITIONS.get(current, [])

    async def create_invoice(
        self,
        db: AsyncSession,
        merchant: Merchant,
        amount_xmr_raw: str | float | Decimal,
        description: str | None = None,
        expires_in: int | None = None,
        metadata: dict[str, Any] | None = None,
        fiat_rate: Decimal | None = None,
        fiat_currency: str = "USD",
    ) -> Invoice:
        """Create a new invoice with a unique subaddress.

        Args:
            db: Async DB session (caller manages commit/rollback).
            merchant: Authenticated merchant object.
            amount_xmr_raw: XMR amount (string recommended for precision).
            description: Optional invoice description.
            expires_in: Seconds until expiry (600–86400, default 3600).
            metadata: Optional merchant-defined JSONB data.
            fiat_rate: Current XMR/fiat rate (from Redis price cache).
            fiat_currency: Fiat currency code (default "USD").

        Returns:
            Created Invoice ORM object (with address relationship loaded).

        Raises:
            InvoiceValidationError: Invalid input.
            WalletUnavailableError: wallet-rpc not reachable.
        """
        # 1. Validate inputs
        amount_xmr = self._parse_amount_xmr(amount_xmr_raw)
        expires_in_sec = self._validate_expires_in(expires_in)
        amount_atomic = xmr_to_atomic(amount_xmr)
        if amount_atomic <= 0:
            raise InvoiceValidationError("amount_xmr is below the minimum atomic unit.")

        # 2. Calculate fiat amount (snapshot at creation)
        fiat_amount: Decimal | None = None
        if fiat_rate is not None and fiat_rate > 0:
            fiat_amount = (amount_xmr * fiat_rate).quantize(Decimal("0.01"))

        # 3. Generate invoice id and wallet label
        invoice_id = uuid.uuid4()
        label = f"inv_{str(invoice_id)[:8]}"

        # 4. Calculate expiration
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_sec)

        # 5. Create Invoice
        invoice = Invoice(
            id=invoice_id,
            merchant_id=merchant.id,
            amount_xmr=amount_xmr,
            amount_atomic=amount_atomic,
            fiat_currency=fiat_currency if fiat_rate else None,
            fiat_amount=fiat_amount,
            fiat_rate=fiat_rate,
            status=InvoiceStatus.pending,
            description=description,
            metadata_json=metadata,
            expires_at=expires_at,
        )
        db.add(invoice)
        await db.flush()

        # 6. Request subaddress from wallet-rpc only after the invoice row is durable in this transaction.
        try:
            rpc = get_monero_rpc()
            addr_result = await rpc.create_address(account_index=0, label=label)
        except MoneroRPCConnectionError as exc:
            await db.delete(invoice)
            await db.flush()
            logger.error("wallet-rpc unavailable during invoice creation: %s", exc)
            raise WalletUnavailableError("Payment system is temporarily unavailable. Please try again later.") from exc
        except MoneroRPCError as exc:
            await db.delete(invoice)
            await db.flush()
            logger.error("wallet-rpc error during create_address: %s", exc)
            raise WalletUnavailableError("Payment system error. Please try again later.") from exc

        subaddress: str = addr_result["address"]
        address_index: int = addr_result["address_index"]

        # 7. Create InvoiceAddress (1:1)
        invoice_address = InvoiceAddress(
            invoice_id=invoice_id,
            address=subaddress,
            address_index=address_index,
            account_index=0,
        )
        db.add(invoice_address)

        # 8. Audit log
        audit = AuditLog(
            merchant_id=merchant.id,
            action="invoice.created",
            entity_type="invoice",
            entity_id=invoice_id,
            details={
                "amount_atomic": amount_atomic,
                "expires_in": expires_in_sec,
                "address_index": address_index,
            },
        )
        db.add(audit)

        await db.flush()

        # Eagerly load the address relationship for response
        await db.refresh(invoice, attribute_names=["address"])

        logger.info(
            "Invoice created: %s, merchant=%s, amount=%s XMR, addr_index=%d",
            invoice_id,
            merchant.id,
            amount_xmr,
            address_index,
        )

        return invoice

    async def get_invoice(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Invoice:
        """Get a single invoice by ID, scoped to merchant.

        Raises InvoiceNotFoundError if not found.
        """
        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.merchant_id == merchant_id)
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if invoice is None:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found.")

        # Load address relationship
        await db.refresh(invoice, attribute_names=["address"])

        return invoice

    async def list_invoices(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        status: InvoiceStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Invoice], int]:
        """List invoices for a merchant with optional status filter.

        Returns:
            Tuple of (invoices list, total count).
        """
        # Clamp limits
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        # Base filter
        base_where = [Invoice.merchant_id == merchant_id]
        if status is not None:
            base_where.append(Invoice.status == status)

        # Count query
        count_stmt = select(func.count(Invoice.id)).where(*base_where)
        total = (await db.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = select(Invoice).where(*base_where).order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(data_stmt)
        invoices = list(result.scalars().all())

        # Load address for each invoice
        for inv in invoices:
            await db.refresh(inv, attribute_names=["address"])

        return invoices, total

    async def cancel_invoice(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> Invoice:
        """Cancel a pending invoice.

        Rules:
            - Only pending invoices can be cancelled.
            - Invoices with any detected/confirmed payments cannot be cancelled.
            - Creates audit log entry.

        Raises:
            InvoiceNotFoundError: Invoice not found.
            InvoiceStateError: Invoice is not in pending status or has payments.
        """
        invoice = await self.get_invoice(db, merchant_id, invoice_id)

        if invoice.status != InvoiceStatus.pending:
            raise InvoiceStateError(
                f"Cannot cancel invoice with status '{invoice.status.value}'. Only pending invoices can be cancelled."
            )

        # Check for existing payments (safety net)
        payment_count_stmt = select(func.count(Payment.id)).where(
            Payment.invoice_id == invoice_id,
            Payment.status.in_([PaymentStatus.detected, PaymentStatus.confirmed]),
        )
        payment_count = (await db.execute(payment_count_stmt)).scalar_one()

        if payment_count > 0:
            raise InvoiceStateError("Cannot cancel invoice that has detected or confirmed payments.")

        # Transition
        invoice.status = InvoiceStatus.cancelled

        # Audit log
        audit = AuditLog(
            merchant_id=merchant_id,
            action="invoice.cancelled",
            entity_type="invoice",
            entity_id=invoice_id,
            details={"previous_status": "pending"},
        )
        db.add(audit)

        await db.flush()

        logger.info("Invoice cancelled: %s, merchant=%s", invoice_id, merchant_id)

        return invoice

    async def update_status(
        self,
        db: AsyncSession,
        invoice: Invoice,
        new_status: InvoiceStatus,
        details: dict[str, Any] | None = None,
    ) -> Invoice:
        """Transition invoice to a new status with validation.

        This method is idempotent: if invoice is already in target status,
        it returns without error.

        Args:
            db: Async DB session.
            invoice: Invoice ORM object.
            new_status: Target status.
            details: Optional audit log details.

        Raises:
            InvoiceStateError: If transition is not allowed.
        """
        # Idempotent: already in target status
        if invoice.status == new_status:
            return invoice

        if not self.can_transition(invoice.status, new_status):
            raise InvoiceStateError(f"Invalid transition: {invoice.status.value} → {new_status.value}")

        old_status = invoice.status
        invoice.status = new_status

        # Set paid_at timestamp for payment-related terminal states
        if new_status in (
            InvoiceStatus.paid,
            InvoiceStatus.overpaid,
            InvoiceStatus.late_paid,
        ):
            invoice.paid_at = datetime.now(timezone.utc)

        # Audit log
        audit = AuditLog(
            merchant_id=invoice.merchant_id,
            action="invoice.status_changed",
            entity_type="invoice",
            entity_id=invoice.id,
            details={
                "from": old_status.value,
                "to": new_status.value,
                **(details or {}),
            },
        )
        db.add(audit)

        await db.flush()

        logger.info(
            "Invoice %s status: %s → %s",
            invoice.id,
            old_status.value,
            new_status.value,
        )

        return invoice


invoice_service = InvoiceService()
