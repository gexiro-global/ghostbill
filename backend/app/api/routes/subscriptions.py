"""
Subscription API routes.

POST /v1/subscriptions              — Create subscription (auth required)
GET  /v1/subscriptions              — List subscriptions (auth required)
GET  /v1/subscriptions/{id}         — Get subscription detail + payments (auth required)
POST /v1/subscriptions/{id}/pause   — Pause subscription (auth required)
POST /v1/subscriptions/{id}/resume  — Resume subscription (auth required)
POST /v1/subscriptions/{id}/cancel  — Cancel subscription (auth required)
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
from app.db.models import Merchant, SubscriptionStatus
from app.db.session import get_db
from app.dependencies import get_redis
from app.services.invoice_service import WalletUnavailableError
from app.services.subscription_service import (
    SubscriptionNotFoundError,
    SubscriptionStateError,
    SubscriptionValidationError,
    subscription_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# ─── Request / Response schemas ──────────────────────────────────────────────


class SubscriptionCreateRequest(BaseModel):
    customer_id: str = Field(..., description="Customer UUID")
    amount_xmr: str = Field(
        ..., description="XMR amount per period", examples=["0.5"]
    )
    interval_days: int = Field(..., ge=1, description="Billing interval in days")
    grace_days_soft: int = Field(default=3, ge=0, description="Days before past_due")
    grace_days_hard: int = Field(default=7, ge=0, description="Days before expired")
    start_at: str | None = Field(
        default=None, description="ISO datetime, default=now (immediate first invoice)"
    )
    metadata: dict | None = Field(default=None, description="Arbitrary metadata")


class SubscriptionResponse(BaseModel):
    id: str
    merchant_id: str
    customer_id: str
    amount_xmr: str
    amount_atomic: int
    interval_days: int
    status: str
    grace_days_soft: int
    grace_days_hard: int
    next_due_at: str | None
    cancelled_at: str | None
    metadata: dict | None
    created_at: str
    updated_at: str


class SubscriptionDetailResponse(SubscriptionResponse):
    customer: dict | None = None
    payments: list[dict] = []


class SubscriptionListResponse(BaseModel):
    subscriptions: list[SubscriptionResponse]
    total: int
    limit: int
    offset: int


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _sub_to_response(sub) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=str(sub.id),
        merchant_id=str(sub.merchant_id),
        customer_id=str(sub.customer_id),
        amount_xmr=str(sub.amount_xmr),
        amount_atomic=sub.amount_atomic,
        interval_days=sub.interval_days,
        status=sub.status.value,
        grace_days_soft=sub.grace_days_soft,
        grace_days_hard=sub.grace_days_hard,
        next_due_at=sub.next_due_at.isoformat() if sub.next_due_at else None,
        cancelled_at=sub.cancelled_at.isoformat() if sub.cancelled_at else None,
        metadata=sub.metadata_json,
        created_at=sub.created_at.isoformat(),
        updated_at=sub.updated_at.isoformat(),
    )


def _parse_start_at(raw: str | None) -> "datetime | None":
    """Parse optional ISO datetime string."""
    if raw is None:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid start_at datetime: {raw!r}",
        )


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SubscriptionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    body: SubscriptionCreateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new subscription. Generates first invoice immediately if start_at <= now."""
    try:
        customer_uuid = uuid.UUID(body.customer_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer_id format.",
        )

    start_at = _parse_start_at(body.start_at)

    try:
        sub = await subscription_service.create_subscription(
            db=db,
            merchant=merchant,
            customer_id=customer_uuid,
            amount_xmr_raw=body.amount_xmr,
            interval_days=body.interval_days,
            grace_days_soft=body.grace_days_soft,
            grace_days_hard=body.grace_days_hard,
            start_at=start_at,
            metadata=body.metadata,
        )
        await db.commit()
    except SubscriptionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except SubscriptionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except WalletUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    # Fetch full detail (with customer + payments)
    detail = await subscription_service.get_subscription(db, merchant.id, sub.id)
    resp = _sub_to_response(detail["subscription"])
    return SubscriptionDetailResponse(
        **resp.model_dump(),
        customer=detail["customer"],
        payments=detail["payments"],
    )


@router.get("", response_model=SubscriptionListResponse)
async def list_subscriptions(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    sub_status: str | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    customer_id: uuid.UUID | None = Query(default=None, description="Filter by customer"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List subscriptions for the authenticated merchant."""
    status_filter: SubscriptionStatus | None = None
    if sub_status is not None:
        try:
            status_filter = SubscriptionStatus(sub_status)
        except ValueError:
            valid = ", ".join(s.value for s in SubscriptionStatus)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{sub_status}'. Valid: {valid}",
            )

    subs, total = await subscription_service.list_subscriptions(
        db=db,
        merchant_id=merchant.id,
        status=status_filter,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )

    return SubscriptionListResponse(
        subscriptions=[_sub_to_response(s) for s in subs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{subscription_id}", response_model=SubscriptionDetailResponse)
async def get_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get subscription detail with customer info and payment history."""
    try:
        detail = await subscription_service.get_subscription(
            db=db, merchant_id=merchant.id, subscription_id=subscription_id
        )
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found.",
        )

    resp = _sub_to_response(detail["subscription"])
    return SubscriptionDetailResponse(
        **resp.model_dump(),
        customer=detail["customer"],
        payments=detail["payments"],
    )


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse)
async def pause_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Pause an active subscription."""
    try:
        sub = await subscription_service.pause_subscription(
            db=db, merchant_id=merchant.id, subscription_id=subscription_id
        )
        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found.",
        )
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return _sub_to_response(sub)


@router.post("/{subscription_id}/resume", response_model=SubscriptionResponse)
async def resume_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused subscription."""
    try:
        sub = await subscription_service.resume_subscription(
            db=db, merchant_id=merchant.id, subscription_id=subscription_id
        )
        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found.",
        )
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return _sub_to_response(sub)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a subscription. Terminal state — cannot be undone."""
    try:
        sub = await subscription_service.cancel_subscription(
            db=db, merchant_id=merchant.id, subscription_id=subscription_id
        )
        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found.",
        )
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return _sub_to_response(sub)
