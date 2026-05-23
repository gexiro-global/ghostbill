"""Invoice API routes.

POST /v1/invoices              — Create new invoice (auth required)
GET  /v1/invoices              — List invoices with cursor pagination (auth required)
GET  /v1/invoices/{id}         — Get single invoice with payments (auth required)
POST /v1/invoices/{id}/cancel  — Cancel pending invoice (auth required)
"""

import json
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.api.routes.invoice_schemas import (
    InvoiceCreateRequest,
    InvoiceCursorResponse,
    InvoiceDetailResponse,
    InvoiceResponse,
    PaymentSummary,
)
from app.db.models import Invoice, InvoiceStatus, Merchant
from app.db.session import get_db
from app.dependencies import get_redis
from app.services.invoice_service import (
    InvoiceNotFoundError,
    InvoiceStateError,
    InvoiceValidationError,
    WalletUnavailableError,
    invoice_service,
)
from app.utils.pagination import paginate_cursor, validate_cursor_params

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["invoices"])


# ─── Helpers ───────────────────────────────────────────────────────────


def _invoice_to_response(invoice) -> InvoiceResponse:
    """Convert Invoice ORM object to response schema (list view)."""
    addr = invoice.address
    return InvoiceResponse(
        id=str(invoice.id),
        merchant_id=str(invoice.merchant_id),
        amount_xmr=str(invoice.amount_xmr),
        amount_atomic=invoice.amount_atomic,
        fiat_currency=invoice.fiat_currency,
        fiat_amount=str(invoice.fiat_amount) if invoice.fiat_amount is not None else None,
        fiat_rate=str(invoice.fiat_rate) if invoice.fiat_rate is not None else None,
        status=invoice.status.value,
        description=invoice.description,
        metadata=invoice.metadata_json,
        address=addr.address if addr else None,
        address_index=addr.address_index if addr else None,
        expires_at=invoice.expires_at.isoformat(),
        paid_at=invoice.paid_at.isoformat() if invoice.paid_at else None,
        created_at=invoice.created_at.isoformat(),
        updated_at=invoice.updated_at.isoformat(),
    )


def _invoice_to_detail_response(invoice) -> InvoiceDetailResponse:
    """Convert Invoice ORM object to detail response with payments."""
    addr = invoice.address
    payments = invoice.payments or []

    paid_atomic = sum(p.amount_atomic for p in payments if p.status.value != "orphaned")
    paid_xmr = Decimal(paid_atomic) / Decimal(10**12)

    payment_summaries = [
        PaymentSummary(
            id=str(p.id),
            tx_hash=p.tx_hash,
            amount_atomic=p.amount_atomic,
            amount_xmr=str(p.amount_xmr),
            status=p.status.value,
            confirmations=p.confirmations,
            block_height=p.block_height,
            detected_at=p.detected_at.isoformat(),
            confirmed_at=p.confirmed_at.isoformat() if p.confirmed_at else None,
        )
        for p in payments
    ]

    return InvoiceDetailResponse(
        id=str(invoice.id),
        merchant_id=str(invoice.merchant_id),
        amount_xmr=str(invoice.amount_xmr),
        amount_atomic=invoice.amount_atomic,
        fiat_currency=invoice.fiat_currency,
        fiat_amount=str(invoice.fiat_amount) if invoice.fiat_amount is not None else None,
        fiat_rate=str(invoice.fiat_rate) if invoice.fiat_rate is not None else None,
        status=invoice.status.value,
        description=invoice.description,
        metadata=invoice.metadata_json,
        address=addr.address if addr else None,
        address_index=addr.address_index if addr else None,
        expires_at=invoice.expires_at.isoformat(),
        paid_at=invoice.paid_at.isoformat() if invoice.paid_at else None,
        created_at=invoice.created_at.isoformat(),
        updated_at=invoice.updated_at.isoformat(),
        paid_atomic=paid_atomic,
        paid_xmr=str(paid_xmr),
        payments=payment_summaries,
    )


async def _get_fiat_rate(redis: Redis) -> Decimal | None:
    """Read current XMR/USD rate from Redis price cache."""
    raw = await redis.get("xmr_price")
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if data.get("stale", False):
        return None
    usd = data.get("usd")
    if usd is None:
        return None
    try:
        return Decimal(str(usd))
    except Exception:
        return None


# ─── Routes ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    body: InvoiceCreateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Create a new invoice with a unique Monero subaddress."""
    fiat_rate = await _get_fiat_rate(redis)
    try:
        invoice = await invoice_service.create_invoice(
            db=db,
            merchant=merchant,
            amount_xmr_raw=body.amount_xmr,
            description=body.description,
            expires_in=body.expires_in,
            metadata=body.metadata,
            fiat_rate=fiat_rate,
            fiat_currency="USD",
        )
        await db.commit()
    except InvoiceValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except WalletUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return _invoice_to_response(invoice)


@router.get("", response_model=InvoiceCursorResponse)
async def list_invoices(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    invoice_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
):
    """List invoices with cursor pagination."""
    validate_cursor_params(starting_after, ending_before)

    status_filter: InvoiceStatus | None = None
    if invoice_status is not None:
        try:
            status_filter = InvoiceStatus(invoice_status)
        except ValueError:
            valid = ", ".join(s.value for s in InvoiceStatus)
            raise HTTPException(status_code=400, detail=f"Invalid status '{invoice_status}'. Valid: {valid}")

    base_query = select(Invoice).where(Invoice.merchant_id == merchant.id)
    if status_filter is not None:
        base_query = base_query.where(Invoice.status == status_filter)

    result = await paginate_cursor(
        db=db,
        base_query=base_query,
        model=Invoice,
        limit=limit,
        starting_after=starting_after,
        ending_before=ending_before,
        tenant_filter=Invoice.merchant_id == merchant.id,
    )

    # Load address for each invoice
    for inv in result["data"]:
        await db.refresh(inv, attribute_names=["address"])

    return InvoiceCursorResponse(
        data=[_invoice_to_response(inv) for inv in result["data"]],
        has_more=result["has_more"],
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single invoice by ID, including payments and paid amount."""
    try:
        invoice = await invoice_service.get_invoice(db=db, merchant_id=merchant.id, invoice_id=invoice_id)
    except InvoiceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")
    # Eager load payments for detail view
    await db.refresh(invoice, attribute_names=["payments"])
    return _invoice_to_detail_response(invoice)


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending invoice. Only pending invoices with no payments can be cancelled."""
    try:
        invoice = await invoice_service.cancel_invoice(db=db, merchant_id=merchant.id, invoice_id=invoice_id)
        await db.commit()
    except InvoiceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")
    except InvoiceStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Re-fetch with address loaded (avoids greenlet error after commit)
    invoice = await invoice_service.get_invoice(db, merchant.id, invoice_id)
    return _invoice_to_response(invoice)
