"""
Payment API routes — read-only endpoints.

Endpoints:
    GET /v1/payments            — list payments for merchant (filter: invoice_id, status)
    GET /v1/payments/{id}       — get single payment by ID

All endpoints require Bearer auth (merchant scope).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.db.models import Merchant, PaymentStatus
from app.dependencies import get_db
from app.services.payment_service import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

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


class PaymentListResponse(BaseModel):
    payments: list[PaymentResponse]
    total: int
    limit: int
    offset: int


# ─── Helpers ─────────────────────────────────────────────────────────────────

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


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=PaymentListResponse)
async def list_payments(
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    status: Optional[str] = Query(None, description="Filter by status: detected, confirmed, orphaned"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """List payments for the authenticated merchant."""
    # Parse optional invoice_id
    parsed_invoice_id: uuid.UUID | None = None
    if invoice_id:
        try:
            parsed_invoice_id = uuid.UUID(invoice_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid invoice_id format.")

    # Parse optional status
    parsed_status: PaymentStatus | None = None
    if status:
        try:
            parsed_status = PaymentStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(s.value for s in PaymentStatus)}",
            )

    payments, total = await payment_service.list_payments(
        db=db,
        merchant_id=merchant.id,
        invoice_id=parsed_invoice_id,
        status=parsed_status,
        limit=limit,
        offset=offset,
    )

    return PaymentListResponse(
        payments=[_payment_to_response(p) for p in payments],
        total=total,
        limit=limit,
        offset=offset,
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
