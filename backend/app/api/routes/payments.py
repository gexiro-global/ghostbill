"""Payment API routes — read-only endpoints with cursor pagination.

Endpoints:
    GET /v1/payments            — list payments for merchant (filter: invoice_id, status)
    GET /v1/payments/{id}       — get single payment by ID

All endpoints require Bearer auth (merchant scope).
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.db.models import Invoice, Merchant, Payment, PaymentStatus
from app.dependencies import get_db
from app.services.payment_service import payment_service
from app.utils.pagination import paginate_cursor, validate_cursor_params

router = APIRouter(prefix="/payments", tags=["payments"])


# ─── Schemas ──────────────────────────────────────────────────────────


class PaymentResponse(BaseModel):
    id: str
    invoice_id: str
    tx_hash: str
    amount_atomic: int
    amount_xmr: str
    status: str
    confirmations: int
    block_height: Optional[int] = None
    detected_at: Optional[str] = None
    confirmed_at: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class PaymentCursorResponse(BaseModel):
    data: list[PaymentResponse]
    has_more: bool


# ─── Helpers ──────────────────────────────────────────────────────────


def _payment_to_response(payment) -> PaymentResponse:
    return PaymentResponse(
        id=str(payment.id),
        invoice_id=str(payment.invoice_id),
        tx_hash=payment.tx_hash,
        amount_atomic=payment.amount_atomic,
        amount_xmr=str(payment.amount_xmr),
        status=payment.status.value,
        confirmations=payment.confirmations,
        block_height=payment.block_height,
        detected_at=payment.detected_at.isoformat() if payment.detected_at else None,
        confirmed_at=payment.confirmed_at.isoformat() if payment.confirmed_at else None,
        created_at=payment.created_at.isoformat() if payment.created_at else None,
    )


# ─── Routes ───────────────────────────────────────────────────────────


@router.get("", response_model=PaymentCursorResponse)
async def list_payments(
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    status: Optional[str] = Query(None, description="Filter by status: detected, confirmed, orphaned"),
    limit: int = Query(50, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """List payments for the authenticated merchant with cursor pagination."""
    validate_cursor_params(starting_after, ending_before)

    parsed_invoice_id: uuid.UUID | None = None
    if invoice_id:
        try:
            parsed_invoice_id = uuid.UUID(invoice_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid invoice_id format.")

    parsed_status: PaymentStatus | None = None
    if status:
        try:
            parsed_status = PaymentStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(s.value for s in PaymentStatus)}",
            )

    # Build base query: payments scoped to merchant via invoice join
    base_query = (
        select(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Invoice.merchant_id == merchant.id)
    )
    if parsed_invoice_id is not None:
        base_query = base_query.where(Payment.invoice_id == parsed_invoice_id)
    if parsed_status is not None:
        base_query = base_query.where(Payment.status == parsed_status)

    result = await paginate_cursor(
        db=db, base_query=base_query, model=Payment,
        limit=limit, starting_after=starting_after, ending_before=ending_before,
    )

    return PaymentCursorResponse(
        data=[_payment_to_response(p) for p in result["data"]],
        has_more=result["has_more"],
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single payment by ID."""
    try:
        pid = uuid.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment ID format.")

    payment = await payment_service.get_payment(db, merchant.id, pid)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found.")
    return _payment_to_response(payment)
