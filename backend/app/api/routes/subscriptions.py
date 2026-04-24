"""Subscription API routes.

POST   /v1/subscriptions              — Create
GET    /v1/subscriptions              — List (cursor pagination)
GET    /v1/subscriptions/{id}         — Detail + payments
PATCH  /v1/subscriptions/{id}         — Update (pending changes) [Phase 6A]
POST   /v1/subscriptions/{id}/pause   — Pause
POST   /v1/subscriptions/{id}/resume  — Resume
POST   /v1/subscriptions/{id}/cancel  — Cancel
GET    /v1/subscriptions/{id}/renewal-log — Renewal event log [Phase 6C]
POST   /v1/subscriptions/{id}/prepay  — Pre-pay N periods [Phase 8B]
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.api.routes.subscription_schemas import (
    PrepayRequest,
    PrepayResponse,
    SubscriptionCreateRequest,
    SubscriptionCursorResponse,
    SubscriptionDetailResponse,
    SubscriptionResponse,
    SubscriptionUpdateRequest,
)
from app.db.models import (
    Merchant,
    Subscription,
    SubscriptionRenewalEvent,
    SubscriptionStatus,
)
from app.db.session import get_db
from app.services.invoice_service import WalletUnavailableError
from app.services.subscription_exceptions import (
    SubscriptionNotFoundError,
    SubscriptionStateError,
    SubscriptionValidationError,
)
from app.services.subscription_prepay import create_prepay_invoice
from app.services.subscription_service import subscription_service
from app.services.subscription_update import update_subscription
from app.services.webhook_payloads import build_subscription_updated_payload
from app.services.webhook_service import webhook_service
from app.utils.pagination import paginate_cursor, validate_cursor_params

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_pending_changes(sub):
    has_any = any([
        sub.pending_amount_atomic is not None,
        sub.pending_interval_days is not None,
        sub.pending_grace_soft is not None,
        sub.pending_grace_hard is not None,
    ])
    if not has_any:
        return None, False
    changes = {}
    if sub.pending_amount_atomic is not None:
        changes["amount_xmr"] = str(sub.pending_amount_xmr)
        changes["amount_atomic"] = sub.pending_amount_atomic
    if sub.pending_interval_days is not None:
        changes["interval_days"] = sub.pending_interval_days
    if sub.pending_grace_soft is not None:
        changes["grace_days_soft"] = sub.pending_grace_soft
    if sub.pending_grace_hard is not None:
        changes["grace_days_hard"] = sub.pending_grace_hard
    return changes, True


def _sub_to_response(sub) -> SubscriptionResponse:
    pending, has_pending = _build_pending_changes(sub)
    return SubscriptionResponse(
        id=str(sub.id), merchant_id=str(sub.merchant_id),
        customer_id=str(sub.customer_id), amount_xmr=str(sub.amount_xmr),
        amount_atomic=sub.amount_atomic, interval_days=sub.interval_days,
        status=sub.status.value, grace_days_soft=sub.grace_days_soft,
        grace_days_hard=sub.grace_days_hard,
        billing_anchor_at=sub.billing_anchor_at.isoformat() if sub.billing_anchor_at else None,
        next_due_at=sub.next_due_at.isoformat() if sub.next_due_at else None,
        cancelled_at=sub.cancelled_at.isoformat() if sub.cancelled_at else None,
        trial_days=sub.trial_days,
        trial_end_at=sub.trial_end_at.isoformat() if sub.trial_end_at else None,
        prepaid_until=sub.prepaid_until.isoformat() if sub.prepaid_until else None,
        metadata=sub.metadata_json, pending_changes=pending,
        has_pending_changes=has_pending,
        created_at=sub.created_at.isoformat(), updated_at=sub.updated_at.isoformat(),
    )


def _parse_start_at(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid start_at: {raw!r}")


# ── Phase 6C: Renewal Log Schemas ────────────────────────────────────────


class RenewalEventResponse(BaseModel):
    id: str
    result: str
    invoice_id: str | None = None
    error_message: str | None = None
    details: dict | None = None
    created_at: str


class RenewalLogCursorResponse(BaseModel):
    data: list[RenewalEventResponse]
    has_more: bool


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=SubscriptionDetailResponse, status_code=201)
async def create_subscription(
    body: SubscriptionCreateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        customer_uuid = uuid.UUID(body.customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id format.")
    try:
        sub = await subscription_service.create_subscription(
            db=db, merchant=merchant, customer_id=customer_uuid,
            amount_xmr_raw=body.amount_xmr, interval_days=body.interval_days,
            grace_days_soft=body.grace_days_soft, grace_days_hard=body.grace_days_hard,
            start_at=_parse_start_at(body.start_at), trial_days=body.trial_days,
            metadata=body.metadata,
        )
        await db.commit()
    except SubscriptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SubscriptionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WalletUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    detail = await subscription_service.get_subscription(db, merchant.id, sub.id)
    resp = _sub_to_response(detail["subscription"])
    return SubscriptionDetailResponse(
        **resp.model_dump(), customer=detail["customer"], payments=detail["payments"])


@router.get("", response_model=SubscriptionCursorResponse)
async def list_subscriptions(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    sub_status: str | None = Query(default=None, alias="status"),
    customer_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
):
    """List subscriptions with cursor pagination."""
    validate_cursor_params(starting_after, ending_before)

    status_filter = None
    if sub_status is not None:
        try:
            status_filter = SubscriptionStatus(sub_status)
        except ValueError:
            valid = ", ".join(s.value for s in SubscriptionStatus)
            raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {valid}")

    base_query = select(Subscription).where(Subscription.merchant_id == merchant.id)
    if status_filter is not None:
        base_query = base_query.where(Subscription.status == status_filter)
    if customer_id is not None:
        base_query = base_query.where(Subscription.customer_id == customer_id)

    result = await paginate_cursor(
        db=db, base_query=base_query, model=Subscription,
        limit=limit, starting_after=starting_after, ending_before=ending_before,
    )

    return SubscriptionCursorResponse(
        data=[_sub_to_response(s) for s in result["data"]],
        has_more=result["has_more"],
    )


@router.get("/{subscription_id}", response_model=SubscriptionDetailResponse)
async def get_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        detail = await subscription_service.get_subscription(db, merchant.id, subscription_id)
    except SubscriptionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found.")
    resp = _sub_to_response(detail["subscription"])
    return SubscriptionDetailResponse(
        **resp.model_dump(), customer=detail["customer"], payments=detail["payments"])


@router.get("/{subscription_id}/renewal-log", response_model=RenewalLogCursorResponse)
async def get_renewal_log(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
):
    """Phase 6C: Get renewal event log for a subscription (cursor paginated)."""
    validate_cursor_params(starting_after, ending_before)

    sub_stmt = select(Subscription).where(
        Subscription.id == subscription_id,
        Subscription.merchant_id == merchant.id,
    )
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found.")

    base_query = select(SubscriptionRenewalEvent).where(
        SubscriptionRenewalEvent.subscription_id == subscription_id,
    )

    result = await paginate_cursor(
        db=db, base_query=base_query, model=SubscriptionRenewalEvent,
        limit=limit, starting_after=starting_after, ending_before=ending_before,
    )

    data = [
        RenewalEventResponse(
            id=str(e.id), result=e.result,
            invoice_id=str(e.invoice_id) if e.invoice_id else None,
            error_message=e.error_message, details=e.details,
            created_at=e.created_at.isoformat(),
        )
        for e in result["data"]
    ]

    return RenewalLogCursorResponse(data=data, has_more=result["has_more"])


@router.patch("/{subscription_id}", response_model=SubscriptionResponse)
async def patch_subscription(
    subscription_id: uuid.UUID,
    body: SubscriptionUpdateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Update subscription with pending changes (applied at next renewal)."""
    try:
        sub = await subscription_service._get_for_update(db, merchant.id, subscription_id)
        kwargs = {}
        body_data = body.model_dump(exclude_unset=True)
        for field in ("amount_xmr", "interval_days", "grace_days_soft", "grace_days_hard", "metadata"):
            if field in body_data:
                kwargs[field] = body_data[field]

        sub = await update_subscription(db=db, sub=sub, **kwargs)

        has_financial = any(k in body_data for k in ("amount_xmr", "interval_days", "grace_days_soft", "grace_days_hard"))
        if has_financial:
            payload = build_subscription_updated_payload(sub)
            payload["event"] = "subscription.updated"
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            await webhook_service.queue_webhook(
                db=db, merchant=merchant, event_type="subscription.updated", payload=payload)

        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found.")
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SubscriptionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _sub_to_response(sub)


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse)
async def pause_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        sub = await subscription_service.pause_subscription(db, merchant.id, subscription_id)
        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found.")
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _sub_to_response(sub)


@router.post("/{subscription_id}/resume", response_model=SubscriptionResponse)
async def resume_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        sub = await subscription_service.resume_subscription(db, merchant.id, subscription_id)
        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found.")
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _sub_to_response(sub)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    try:
        sub = await subscription_service.cancel_subscription(db, merchant.id, subscription_id)
        await db.commit()
        await db.refresh(sub)
    except SubscriptionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found.")
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _sub_to_response(sub)


@router.post("/{subscription_id}/prepay", response_model=PrepayResponse, status_code=201)
async def prepay_subscription(
    subscription_id: uuid.UUID,
    body: PrepayRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Phase 8B: Pre-pay N periods with optional discount."""
    try:
        invoice = await create_prepay_invoice(
            db=db, merchant=merchant,
            subscription_id=subscription_id, periods=body.periods,
        )
        # Fire subscription.prepaid webhook
        sub_stmt = select(Subscription).where(Subscription.id == subscription_id)
        sub = (await db.execute(sub_stmt)).scalar_one()
        await webhook_service.dispatch_subscription_event(
            db=db, event_type="subscription.prepaid",
            subscription=sub, invoice_id=invoice.id,
        )
        await db.commit()
    except SubscriptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SubscriptionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SubscriptionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except WalletUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    meta = invoice.metadata_json or {}
    # Re-fetch subscription for prepaid_until
    sub = (await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )).scalar_one()

    return PrepayResponse(
        subscription_id=str(subscription_id),
        invoice_id=str(invoice.id),
        periods=meta.get("periods", body.periods),
        discount_pct=meta.get("discount_pct", 0),
        per_period_xmr=meta.get("per_period_amount_xmr", ""),
        total_xmr=str(invoice.amount_xmr),
        total_atomic=invoice.amount_atomic,
        prepaid_until=sub.prepaid_until.isoformat() if sub.prepaid_until else "",
        invoice_expires_at=invoice.expires_at.isoformat(),
    )
