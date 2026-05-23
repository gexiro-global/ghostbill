"""Webhook API routes — delivery log, manual retry, Dead Letter Queue.

Endpoints:
    GET  /v1/webhooks                         — list deliveries (cursor)
    GET  /v1/webhooks/{id}                    — single delivery details
    POST /v1/webhooks/{id}/retry              — retry a failed delivery
    GET  /v1/webhooks/dead-letters            — list DLQ entries (Phase 6B)
    POST /v1/webhooks/dead-letters/{id}/retry — retry DLQ entry (Phase 6B)

All endpoints require Bearer auth (merchant scope).
"""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.db.models import (
    Merchant,
    WebhookDeadLetter,
    WebhookDelivery,
    WebhookStatus,
)
from app.dependencies import get_db
from app.services.webhook_service import (
    WebhookRetryConflictError,
    WebhookRetryInvalidStateError,
    WebhookRetryNotFoundError,
    webhook_service,
)
from app.utils.pagination import paginate_cursor, validate_cursor_params

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ─── Schemas ──────────────────────────────────────────────────────────


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
    payload_truncated: bool = False
    created_at: Optional[str] = None
    model_config = {"from_attributes": True}


class WebhookCursorResponse(BaseModel):
    data: list[WebhookDeliveryResponse]
    has_more: bool


class DLQEntryResponse(BaseModel):
    id: str
    delivery_id: str
    event_type: str
    payload: dict[str, Any]
    original_created_at: str
    dead_lettered_at: str
    retry_count: int
    last_retry_at: Optional[str] = None
    last_error: Optional[str] = None
    resolved: bool
    resolved_at: Optional[str] = None
    payload_truncated: bool = False


class DLQCursorResponse(BaseModel):
    data: list[DLQEntryResponse]
    has_more: bool


class DLQRetryResponse(BaseModel):
    id: str
    retry_count: int
    status: str
    message: str


# ─── Helpers ──────────────────────────────────────────────────────────


def _truncate_payload(payload: dict[str, Any], limit: int = 200) -> tuple[dict[str, Any], bool]:
    import json

    rendered = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if len(rendered) <= limit:
        return payload, False
    return {"truncated": rendered[:limit]}, True


def _delivery_to_response(d, truncate: bool = False) -> WebhookDeliveryResponse:
    payload, payload_truncated = _truncate_payload(d.payload) if truncate else (d.payload, False)
    return WebhookDeliveryResponse(
        id=str(d.id),
        merchant_id=str(d.merchant_id),
        invoice_id=str(d.invoice_id) if d.invoice_id else None,
        event_type=d.event_type,
        payload=payload,
        url=d.url,
        status=d.status.value,
        attempts=d.attempts,
        max_attempts=d.max_attempts,
        last_attempt_at=d.last_attempt_at.isoformat() if d.last_attempt_at else None,
        next_retry_at=d.next_retry_at.isoformat() if d.next_retry_at else None,
        response_code=d.response_code,
        response_body=None if truncate else d.response_body,
        payload_truncated=payload_truncated,
        created_at=d.created_at.isoformat() if d.created_at else None,
    )


def _dlq_to_response(entry: WebhookDeadLetter, truncate: bool = False) -> DLQEntryResponse:
    payload, payload_truncated = _truncate_payload(entry.payload) if truncate else (entry.payload, False)
    return DLQEntryResponse(
        id=str(entry.id),
        delivery_id=str(entry.delivery_id),
        event_type=entry.event_type,
        payload=payload,
        original_created_at=entry.original_created_at.isoformat(),
        dead_lettered_at=entry.dead_lettered_at.isoformat(),
        retry_count=entry.retry_count,
        last_retry_at=entry.last_retry_at.isoformat() if entry.last_retry_at else None,
        last_error=entry.last_error,
        resolved=entry.resolved,
        resolved_at=entry.resolved_at.isoformat() if entry.resolved_at else None,
        payload_truncated=payload_truncated,
    )


# ─── DLQ routes (must be BEFORE /{delivery_id} to avoid path collision) ───


@router.get("/dead-letters", response_model=DLQCursorResponse)
async def list_dead_letters(
    resolved: Optional[bool] = Query(default=None, description="Filter by resolved status"),
    limit: int = Query(50, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """List dead-lettered webhooks for the authenticated merchant."""
    validate_cursor_params(starting_after, ending_before)

    base_query = select(WebhookDeadLetter).where(WebhookDeadLetter.merchant_id == merchant.id)
    if resolved is None:
        base_query = base_query.where(WebhookDeadLetter.resolved.is_(False))
    else:
        base_query = base_query.where(WebhookDeadLetter.resolved == resolved)

    result = await paginate_cursor(
        db=db,
        base_query=base_query,
        model=WebhookDeadLetter,
        limit=limit,
        starting_after=starting_after,
        ending_before=ending_before,
        tenant_filter=WebhookDeadLetter.merchant_id == merchant.id,
    )

    return DLQCursorResponse(
        data=[_dlq_to_response(e, truncate=True) for e in result["data"]],
        has_more=result["has_more"],
    )


@router.post("/dead-letters/{dlq_id}/retry", response_model=DLQRetryResponse)
async def retry_dead_letter(
    dlq_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Retry a dead-lettered webhook. Single attempt, no 7-retry cycle."""
    entry = (
        await db.execute(
            select(WebhookDeadLetter).where(
                WebhookDeadLetter.id == dlq_id,
                WebhookDeadLetter.merchant_id == merchant.id,
            )
        )
    ).scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="Dead letter entry not found.")
    if entry.resolved:
        raise HTTPException(status_code=409, detail="Already resolved.")

    try:
        await webhook_service.retry_dead_letter(db, merchant, entry)
    except WebhookRetryConflictError:
        raise HTTPException(status_code=409, detail="Already resolved.")
    except WebhookRetryInvalidStateError:
        raise HTTPException(status_code=400, detail="Webhook URL not configured.")

    await db.commit()

    return DLQRetryResponse(
        id=str(entry.id),
        retry_count=entry.retry_count,
        status="retrying",
        message="Webhook re-queued for delivery",
    )


# ─── Delivery routes ──────────────────────────────────────────────────


@router.get("", response_model=WebhookCursorResponse)
async def list_webhook_deliveries(
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """List webhook deliveries with cursor pagination."""
    validate_cursor_params(starting_after, ending_before)

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

    base_query = select(WebhookDelivery).where(WebhookDelivery.merchant_id == merchant.id)
    if parsed_invoice_id is not None:
        base_query = base_query.where(WebhookDelivery.invoice_id == parsed_invoice_id)
    if parsed_status is not None:
        base_query = base_query.where(WebhookDelivery.status == parsed_status)

    result = await paginate_cursor(
        db=db,
        base_query=base_query,
        model=WebhookDelivery,
        limit=limit,
        starting_after=starting_after,
        ending_before=ending_before,
        tenant_filter=WebhookDelivery.merchant_id == merchant.id,
    )

    return WebhookCursorResponse(
        data=[_delivery_to_response(d, truncate=True) for d in result["data"]],
        has_more=result["has_more"],
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

    stmt = select(WebhookDelivery).where(WebhookDelivery.id == did, WebhookDelivery.merchant_id == merchant.id)
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found.")
    return _delivery_to_response(delivery)


@router.post("/{delivery_id}/retry", response_model=WebhookDeliveryResponse)
async def retry_webhook_delivery(
    delivery_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Manually retry a failed webhook delivery."""
    try:
        did = uuid.UUID(delivery_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid delivery ID format.")

    try:
        delivery = await webhook_service.retry_delivery(db, merchant.id, did)
    except WebhookRetryNotFoundError:
        raise HTTPException(status_code=404, detail="Webhook delivery not found.")
    except WebhookRetryConflictError:
        raise HTTPException(status_code=409, detail="Delivery already completed.")
    except WebhookRetryInvalidStateError:
        raise HTTPException(status_code=400, detail="Delivery not in failed/dead_lettered status.")
    await db.commit()
    return _delivery_to_response(delivery)
