"""
Webhook API routes — delivery log and manual retry.

Endpoints:
    GET  /v1/webhooks           — list webhook deliveries (filter: invoice_id, status)
    GET  /v1/webhooks/{id}      — get single delivery details (with raw payload)
    POST /v1/webhooks/{id}/retry — manually retry a failed delivery

All endpoints require Bearer auth (merchant scope).
"""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.db.models import Merchant, WebhookStatus
from app.dependencies import get_db
from app.services.webhook_service import webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class WebhookDeliveryResponse(BaseModel):
    id: str
    merchant_id: str
    invoice_id: Optional[str] = None
    event_type: str
    payload: dict[str, Any]
    url: str
    status: str
    attempts: int
    max_attempts: int
    last_attempt_at: Optional[str] = None
    next_retry_at: Optional[str] = None
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class WebhookListResponse(BaseModel):
    deliveries: list[WebhookDeliveryResponse]
    total: int
    limit: int
    offset: int


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _delivery_to_response(d) -> WebhookDeliveryResponse:
    return WebhookDeliveryResponse(
        id=str(d.id),
        merchant_id=str(d.merchant_id),
        invoice_id=str(d.invoice_id) if d.invoice_id else None,
        event_type=d.event_type,
        payload=d.payload,
        url=d.url,
        status=d.status.value,
        attempts=d.attempts,
        max_attempts=d.max_attempts,
        last_attempt_at=d.last_attempt_at.isoformat() if d.last_attempt_at else None,
        next_retry_at=d.next_retry_at.isoformat() if d.next_retry_at else None,
        response_code=d.response_code,
        response_body=d.response_body,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=WebhookListResponse)
async def list_webhook_deliveries(
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    status: Optional[str] = Query(None, description="Filter by status: pending, delivered, failed"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """List webhook deliveries for the authenticated merchant."""
    parsed_invoice_id: uuid.UUID | None = None
    if invoice_id:
        try:
            parsed_invoice_id = uuid.UUID(invoice_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid invoice_id format.")

    parsed_status: WebhookStatus | None = None
    if status:
        try:
            parsed_status = WebhookStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(s.value for s in WebhookStatus)}",
            )

    deliveries, total = await webhook_service.list_deliveries(
        db=db,
        merchant_id=merchant.id,
        invoice_id=parsed_invoice_id,
        status=parsed_status,
        limit=limit,
        offset=offset,
    )

    return WebhookListResponse(
        deliveries=[_delivery_to_response(d) for d in deliveries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{delivery_id}", response_model=WebhookDeliveryResponse)
async def get_webhook_delivery(
    delivery_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single webhook delivery with full payload."""
    try:
        did = uuid.UUID(delivery_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid delivery ID format.")

    from sqlalchemy import select
    from app.db.models import WebhookDelivery

    stmt = select(WebhookDelivery).where(
        WebhookDelivery.id == did,
        WebhookDelivery.merchant_id == merchant.id,
    )
    result = await db.execute(stmt)
    delivery = result.scalar_one_or_none()

    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found.")

    return _delivery_to_response(delivery)


@router.post("/{delivery_id}/retry", response_model=WebhookDeliveryResponse)
async def retry_webhook_delivery(
    delivery_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Manually retry a failed webhook delivery.

    Only deliveries with status='failed' can be retried.
    Resets attempts to 0 and schedules immediate retry.
    """
    try:
        did = uuid.UUID(delivery_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid delivery ID format.")

    delivery = await webhook_service.retry_delivery(db, merchant.id, did)

    if delivery is None:
        raise HTTPException(
            status_code=400,
            detail="Webhook delivery not found or not in failed status.",
        )

    await db.commit()

    return _delivery_to_response(delivery)
