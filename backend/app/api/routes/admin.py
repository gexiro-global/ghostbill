"""Admin API routes — instance operator panel.

All endpoints require admin authentication:
    Merchant must match ADMIN_MERCHANT_ID from .env.

GET  /v1/admin/merchants     — List all merchants on this instance
GET  /v1/admin/stats         — Global stats (invoices, payments, subs, revenue)
GET  /v1/admin/health        — Detailed system health (DB, Redis, wallet-rpc, detection)
GET  /v1/admin/me            — Check if current merchant is admin
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
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


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/me", response_model=AdminMeResponse)
async def admin_check(
    merchant: Merchant = Depends(get_current_merchant),
):
    """Check if current merchant has admin access. No 403 — just returns bool."""
    is_admin = (
        bool(settings.admin_merchant_id)
        and str(merchant.id) == settings.admin_merchant_id
    )
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
        inv_count = (await db.execute(
            select(func.count(Invoice.id)).where(Invoice.merchant_id == m.id)
        )).scalar_one()
        sub_count = (await db.execute(
            select(func.count(Subscription.id)).where(Subscription.merchant_id == m.id)
        )).scalar_one()
        result.append(AdminMerchantInfo(
            id=str(m.id), name=m.name, email=m.email,
            is_active=m.is_active, invoice_count=inv_count,
            subscription_count=sub_count,
            created_at=m.created_at.isoformat(),
        ))

    return AdminMerchantsResponse(merchants=result, total=len(result))


@router.get("/stats", response_model=AdminStatsResponse)
async def global_stats(
    merchant: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Global instance statistics."""
    # Merchants
    merchants_total = (await db.execute(
        select(func.count(Merchant.id))
    )).scalar_one()
    merchants_active = (await db.execute(
        select(func.count(Merchant.id)).where(Merchant.is_active == True)
    )).scalar_one()

    # Invoices
    invoices_total = (await db.execute(
        select(func.count(Invoice.id))
    )).scalar_one()
    invoices_paid = (await db.execute(
        select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.paid)
    )).scalar_one()
    invoices_pending = (await db.execute(
        select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.pending)
    )).scalar_one()
    invoices_expired = (await db.execute(
        select(func.count(Invoice.id)).where(Invoice.status == InvoiceStatus.expired)
    )).scalar_one()

    # Payments
    payments_total = (await db.execute(
        select(func.count(Payment.id))
    )).scalar_one()
    payments_confirmed = (await db.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.confirmed)
    )).scalar_one()

    # Revenue
    revenue_row = (await db.execute(
        select(func.coalesce(func.sum(Payment.amount_atomic), 0))
        .where(Payment.status == PaymentStatus.confirmed)
    )).scalar_one()
    total_revenue_atomic = int(revenue_row)
    total_revenue_xmr = f"{total_revenue_atomic / 1e12:.12f}"

    # Subscriptions
    subs_total = (await db.execute(
        select(func.count(Subscription.id))
    )).scalar_one()
    subs_active = (await db.execute(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.active)
    )).scalar_one()
    subs_trialing = (await db.execute(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.trialing)
    )).scalar_one()

    # Webhooks
    wh_pending = (await db.execute(
        select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == WebhookStatus.pending)
    )).scalar_one()
    dlq_unresolved = (await db.execute(
        select(func.count(WebhookDeadLetter.id)).where(WebhookDeadLetter.resolved == False)
    )).scalar_one()

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
    from app.tasks.detection_helpers import get_health_metrics
    from app.dependencies import get_redis

    # Detection
    detection = await get_health_metrics()

    # Database
    try:
        db_result = await db.execute(text("SELECT 1"))
        pool = db.get_bind().pool
        db_info = {
            "connected": True,
            "pool_size": pool.size() if hasattr(pool, 'size') else "unknown",
            "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else "unknown",
        }
    except Exception as exc:
        db_info = {"connected": False, "error": str(exc)}

    # Redis
    try:
        redis = await get_redis()
        redis_info_raw = await redis.info("memory")
        redis_info = {
            "connected": True,
            "used_memory_human": redis_info_raw.get("used_memory_human", "unknown"),
            "connected_clients": (await redis.info("clients")).get("connected_clients", 0),
        }
    except Exception as exc:
        redis_info = {"connected": False, "error": str(exc)}

    # Wallet-RPC
    try:
        from app.services.monero_rpc import get_monero_rpc
        rpc = get_monero_rpc(); height = await rpc.get_height()
        wallet_info = {"connected": True, "height": height}
    except Exception as exc:
        wallet_info = {"connected": False, "error": str(exc)}

    # Background task summary
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
