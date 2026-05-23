"""Admin API routes — instance operator panel.

All endpoints (except /me) require admin authentication:
    Merchant must match ADMIN_MERCHANT_ID from .env.

GET   /v1/admin/me                        — Check admin status
GET   /v1/admin/merchants                 — List all merchants
POST  /v1/admin/merchants/{id}/toggle     — Activate/deactivate merchant
GET   /v1/admin/stats                     — Global stats
GET   /v1/admin/health                    — Detailed system health
GET   /v1/admin/dlq                       — Dead Letter Queue entries
POST  /v1/admin/dlq/{id}/retry            — Retry DLQ entry
POST  /v1/admin/trigger-renewal           — Trigger subscription renewal sweep
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.config import settings
from app.db.models import (
    Invoice,
    InvoiceStatus,
    Merchant,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    WebhookDeadLetter,
    WebhookDelivery,
    WebhookStatus,
)
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Admin Guard ──────────────────────────────────────────────────────────


async def require_admin(merchant: Merchant = Depends(get_current_merchant)) -> Merchant:
    """Dependency: reject non-admin merchants."""
    if not settings.admin_merchant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin panel not configured. Set ADMIN_MERCHANT_ID in .env.",
        )
    if str(merchant.id) != settings.admin_merchant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access denied.",
        )
    return merchant


# ── Response Schemas ───────────────────────────────────────────────────


class AdminMerchantInfo(BaseModel):
    id: str
    name: str
    email: str | None
    is_active: bool
    invoice_count: int
    subscription_count: int
    created_at: str


class AdminMerchantsResponse(BaseModel):
    merchants: list[AdminMerchantInfo]
    total: int


class AdminStatsResponse(BaseModel):
    merchants_total: int
    merchants_active: int
    invoices_total: int
    invoices_paid: int
    invoices_pending: int
    invoices_expired: int
    payments_total: int
    payments_confirmed: int
    total_revenue_atomic: int
    total_revenue_xmr: str
    subscriptions_total: int
    subscriptions_active: int
    subscriptions_trialing: int
    webhook_deliveries_pending: int
    webhook_dlq_unresolved: int


class AdminHealthResponse(BaseModel):
    status: str
    app: str
    version: str
    uptime_info: str
    detection: dict
    database: dict
    redis: dict
    wallet_rpc: dict
    background_tasks: dict


class AdminMeResponse(BaseModel):
    is_admin: bool
    merchant_id: str


class AdminDlqEntry(BaseModel):
    id: str
    delivery_id: str
    merchant_id: str
    merchant_name: str
    event_type: str
    original_created_at: str
    dead_lettered_at: str
    retry_count: int
    last_error: str | None
    resolved: bool


class AdminDlqResponse(BaseModel):
    entries: list[AdminDlqEntry]
    total: int


class AdminActionResponse(BaseModel):
    success: bool
    message: str


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/me", response_model=AdminMeResponse)
async def admin_check(
    merchant: Merchant = Depends(get_current_merchant),
):
    """Check if current merchant has admin access. No 403 — just returns bool."""
    is_admin = bool(settings.admin_merchant_id) and str(merchant.id) == settings.admin_merchant_id
    return AdminMeResponse(is_admin=is_admin, merchant_id=str(merchant.id))


@router.get("/merchants", response_model=AdminMerchantsResponse)
async def list_all_merchants(
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all merchants on this instance with basic stats."""
    merchants_stmt = select(Merchant).order_by(Merchant.created_at.desc())
    merchants = list((await db.execute(merchants_stmt)).scalars().all())

    result = []
    for m in merchants:
        inv_count = (await db.execute(select(func.count(Invoice.id)).where(Invoice.merchant_id == m.id))).scalar_one()
        sub_count = (
            await db.execute(select(func.count(Subscription.id)).where(Subscription.merchant_id == m.id))
        ).scalar_one()
        result.append(
            AdminMerchantInfo(
                id=str(m.id),
                name=m.name,
                email=m.email,
                is_active=m.is_active,
                invoice_count=inv_count,
                subscription_count=sub_count,
                created_at=m.created_at.isoformat(),
            )
        )

    return AdminMerchantsResponse(merchants=result, total=len(result))


@router.post("/merchants/{merchant_id}/toggle", response_model=AdminActionResponse)
async def toggle_merchant_active(
    merchant_id: uuid.UUID,
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle merchant active/inactive status."""
    target = (await db.execute(select(Merchant).where(Merchant.id == merchant_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Merchant not found.")
    if str(merchant_id) == settings.admin_merchant_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate admin merchant.")

    target.is_active = not target.is_active
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()

    action = "activated" if target.is_active else "deactivated"
    logger.info("Admin %s merchant %s (%s)", action, merchant_id, target.name)
    return AdminActionResponse(success=True, message=f"Merchant {action}: {target.name}")


@router.get("/stats", response_model=AdminStatsResponse)
async def global_stats(
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Global instance statistics."""
    merchants_total = (await db.execute(select(func.count(Merchant.id)))).scalar_one()
    merchants_active = (
        await db.execute(select(func.count(Merchant.id)).where(Merchant.is_active == True))
    ).scalar_one()

    invoices_total = (await db.execute(select(func.count(Invoice.id)))).scalar_one()
    invoices_paid = (
        await db.execute(select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.paid))
    ).scalar_one()
    invoices_pending = (
        await db.execute(select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.pending))
    ).scalar_one()
    invoices_expired = (
        await db.execute(select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.expired))
    ).scalar_one()

    payments_total = (await db.execute(select(func.count(Payment.id)))).scalar_one()
    payments_confirmed = (
        await db.execute(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.confirmed))
    ).scalar_one()

    revenue_row = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount_atomic), 0)).where(Payment.status == PaymentStatus.confirmed)
        )
    ).scalar_one()
    total_revenue_atomic = int(revenue_row)
    total_revenue_xmr = f"{total_revenue_atomic / 1e12:.12f}"

    subs_total = (await db.execute(select(func.count(Subscription.id)))).scalar_one()
    subs_active = (
        await db.execute(select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.active))
    ).scalar_one()
    subs_trialing = (
        await db.execute(select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.trialing))
    ).scalar_one()

    wh_pending = (
        await db.execute(select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == WebhookStatus.pending))
    ).scalar_one()
    dlq_unresolved = (
        await db.execute(select(func.count(WebhookDeadLetter.id)).where(WebhookDeadLetter.resolved == False))
    ).scalar_one()

    return AdminStatsResponse(
        merchants_total=merchants_total,
        merchants_active=merchants_active,
        invoices_total=invoices_total,
        invoices_paid=invoices_paid,
        invoices_pending=invoices_pending,
        invoices_expired=invoices_expired,
        payments_total=payments_total,
        payments_confirmed=payments_confirmed,
        total_revenue_atomic=total_revenue_atomic,
        total_revenue_xmr=total_revenue_xmr,
        subscriptions_total=subs_total,
        subscriptions_active=subs_active,
        subscriptions_trialing=subs_trialing,
        webhook_deliveries_pending=wh_pending,
        webhook_dlq_unresolved=dlq_unresolved,
    )


@router.get("/health", response_model=AdminHealthResponse)
async def detailed_health(
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Detailed system health for instance operator."""
    from app.dependencies import get_redis
    from app.tasks.detection_helpers import get_health_metrics

    detection = await get_health_metrics()

    try:
        await db.execute(text("SELECT 1"))
        pool = db.get_bind().pool
        db_info = {
            "connected": True,
            "pool_size": pool.size() if hasattr(pool, "size") else "unknown",
            "checked_out": pool.checkedout() if hasattr(pool, "checkedout") else "unknown",
        }
    except Exception as exc:
        logger.warning("Admin DB health check failed: %s", exc)
        db_info = {"connected": False, "error": "Internal error processing request"}

    try:
        redis = await get_redis()
        redis_info_raw = await redis.info("memory")
        redis_info = {
            "connected": True,
            "used_memory_human": redis_info_raw.get("used_memory_human", "unknown"),
            "connected_clients": (await redis.info("clients")).get("connected_clients", 0),
        }
    except Exception as exc:
        logger.warning("Admin Redis health check failed: %s", exc)
        redis_info = {"connected": False, "error": "Internal error processing request"}

    try:
        from app.services.monero_rpc import get_monero_rpc

        rpc = get_monero_rpc()
        height = await rpc.get_height()
        wallet_info = {"connected": True, "height": height}
    except Exception as exc:
        logger.warning("Admin wallet health check failed: %s", exc)
        wallet_info = {"connected": False, "error": "Internal error processing request"}

    bg_info = {
        "detection_last_sweep": detection.get("last_sweep_at", "unknown"),
        "detection_blocks_behind": detection.get("blocks_behind", "unknown"),
        "tasks_registered": 6,
    }

    return AdminHealthResponse(
        status="healthy",
        app=settings.app_name,
        version=settings.app_version,
        uptime_info="check docker ps for container uptime",
        detection=detection,
        database=db_info,
        redis=redis_info,
        wallet_rpc=wallet_info,
        background_tasks=bg_info,
    )


@router.get("/dlq", response_model=AdminDlqResponse)
async def list_dlq(
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    resolved: bool = Query(default=False, description="Include resolved entries"),
):
    """List Dead Letter Queue entries across all merchants."""
    stmt = (
        select(WebhookDeadLetter, Merchant.name)
        .join(Merchant, WebhookDeadLetter.merchant_id == Merchant.id)
        .order_by(WebhookDeadLetter.dead_lettered_at.desc())
    )
    if not resolved:
        stmt = stmt.where(WebhookDeadLetter.resolved == False)
    stmt = stmt.limit(100)

    rows = (await db.execute(stmt)).all()
    entries = [
        AdminDlqEntry(
            id=str(dlq.id),
            delivery_id=str(dlq.delivery_id),
            merchant_id=str(dlq.merchant_id),
            merchant_name=m_name,
            event_type=dlq.event_type,
            original_created_at=dlq.original_created_at.isoformat(),
            dead_lettered_at=dlq.dead_lettered_at.isoformat(),
            retry_count=dlq.retry_count,
            last_error=dlq.last_error,
            resolved=dlq.resolved,
        )
        for dlq, m_name in rows
    ]

    return AdminDlqResponse(entries=entries, total=len(entries))


@router.post("/dlq/{dlq_id}/retry", response_model=AdminActionResponse)
async def retry_dlq_entry(
    dlq_id: uuid.UUID,
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retry a Dead Letter Queue entry (re-queue for delivery)."""
    dlq_entry = (await db.execute(select(WebhookDeadLetter).where(WebhookDeadLetter.id == dlq_id))).scalar_one_or_none()
    if dlq_entry is None:
        raise HTTPException(status_code=404, detail="DLQ entry not found.")
    if dlq_entry.resolved:
        raise HTTPException(status_code=400, detail="DLQ entry already resolved.")

    # Re-create a pending webhook delivery from the DLQ payload
    target_merchant = (
        await db.execute(select(Merchant).where(Merchant.id == dlq_entry.merchant_id))
    ).scalar_one_or_none()
    if target_merchant is None or not target_merchant.webhook_url:
        raise HTTPException(status_code=400, detail="Merchant has no webhook URL.")

    new_delivery = WebhookDelivery(
        id=uuid.uuid4(),
        merchant_id=dlq_entry.merchant_id,
        event_type=dlq_entry.event_type,
        payload=dlq_entry.payload,
        url=target_merchant.webhook_url,
        status=WebhookStatus.pending,
        attempts=0,
        max_attempts=3,
    )
    db.add(new_delivery)

    dlq_entry.resolved = True
    dlq_entry.resolved_at = datetime.now(timezone.utc)
    dlq_entry.retry_count += 1
    dlq_entry.last_retry_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info("Admin retried DLQ %s → new delivery %s", dlq_id, new_delivery.id)
    return AdminActionResponse(
        success=True,
        message=f"DLQ entry re-queued as delivery {new_delivery.id}",
    )


@router.post("/trigger-renewal", response_model=AdminActionResponse)
async def admin_trigger_renewal(
    merchant: Merchant = Depends(require_admin),
):
    """Trigger subscription renewal sweep from admin panel."""
    from app.tasks.subscription_renewer import run_sweep

    try:
        result = await run_sweep()
        msg = (
            f"Sweep complete: {result.get('renewed', 0)} renewed, "
            f"{result.get('skipped', 0)} skipped, "
            f"{result.get('failed', 0)} failed, "
            f"{result.get('trial_activated', 0)} trials activated"
        )
        return AdminActionResponse(success=True, message=msg)
    except Exception as exc:
        logger.error("Admin trigger renewal failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error processing request")
