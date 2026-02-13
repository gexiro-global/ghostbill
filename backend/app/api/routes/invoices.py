"""
Invoice API routes.

POST /v1/invoices              — Create new invoice (auth required)
GET  /v1/invoices              — List invoices with filters (auth required)
GET  /v1/invoices/{id}         — Get single invoice (auth required)
POST /v1/invoices/{id}/cancel  — Cancel pending invoice (auth required)
"""

import json
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.db.models import InvoiceStatus, Merchant
from app.db.session import get_db
from app.dependencies import get_redis
from app.services.invoice_service import (
    InvoiceNotFoundError,
    InvoiceStateError,
    InvoiceValidationError,
    WalletUnavailableError,
    invoice_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["invoices"])


# ─── Request / Response schemas ──────────────────────────────────────────────


class InvoiceCreateRequest(BaseModel):
    """Create invoice request."""

    amount_xmr: str = Field(
        ...,
        description="XMR amount as string for precision (e.g. '0.5')",
        examples=["0.5", "1.25"],
    )
    description: str | None = Field(
        default=None,
        max_length=1024,
        description="Invoice description",
    )
    expires_in: int | None = Field(
        default=None,
        ge=600,
        le=86400,
        description="Seconds until expiry (600–86400, default 3600)",
    )
    metadata: dict | None = Field(
        default=None,
        description="Merchant-defined metadata (JSONB)",
    )


class InvoiceAddressResponse(BaseModel):
    address: str
    address_index: int


class InvoiceResponse(BaseModel):
    id: str
    merchant_id: str
    amount_xmr: str
    amount_atomic: int
    fiat_currency: str | None
    fiat_amount: str | None
    fiat_rate: str | None
    status: str
    description: str | None
    metadata: dict | None
    address: str | None
    address_index: int | None
    expires_at: str
    paid_at: str | None
    created_at: str
    updated_at: str


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceResponse]
    total: int
    limit: int
    offset: int


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _invoice_to_response(invoice) -> InvoiceResponse:
    """Convert Invoice ORM object to response schema."""
    addr = invoice.address  # InvoiceAddress (1:1 relationship)

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


async def _get_fiat_rate(redis: Redis) -> Decimal | None:
    """Read current XMR/USD rate from Redis price cache.

    Returns None if cache is empty or stale > 10 min.
    Invoice creation proceeds without fiat — XMR amount is authoritative.
    """
    raw = await redis.get("xmr_price")
    if raw is None:
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    # Skip if stale
    if data.get("stale", False):
        return None

    usd = data.get("usd")
    if usd is None:
        return None

    try:
        return Decimal(str(usd))
    except Exception:
        return None


# ─── Routes ──────────────────────────────────────────────────────────────────


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

    # Fetch current fiat rate from Redis (optional, never blocks invoice)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except WalletUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return _invoice_to_response(invoice)


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    invoice_status: str | None = Query(
        default=None,
        alias="status",
        description="Filter by invoice status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List invoices for the authenticated merchant."""

    # Validate status filter if provided
    status_filter: InvoiceStatus | None = None
    if invoice_status is not None:
        try:
            status_filter = InvoiceStatus(invoice_status)
        except ValueError:
            valid = ", ".join(s.value for s in InvoiceStatus)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{invoice_status}'. Valid: {valid}",
            )

    invoices, total = await invoice_service.list_invoices(
        db=db,
        merchant_id=merchant.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    return InvoiceListResponse(
        invoices=[_invoice_to_response(inv) for inv in invoices],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single invoice by ID."""

    try:
        invoice = await invoice_service.get_invoice(
            db=db,
            merchant_id=merchant.id,
            invoice_id=invoice_id,
        )
    except InvoiceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found.",
        )

    return _invoice_to_response(invoice)


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending invoice. Only pending invoices with no payments can be cancelled."""

    try:
        invoice = await invoice_service.cancel_invoice(
            db=db,
            merchant_id=merchant.id,
            invoice_id=invoice_id,
        )
        await db.commit()
    except InvoiceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found.",
        )
    except InvoiceStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Re-fetch with address loaded (avoids greenlet error after commit)
    invoice = await invoice_service.get_invoice(db, merchant.id, invoice_id)
    return _invoice_to_response(invoice)
