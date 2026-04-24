"""Analytics API routes.

Phase 7A: Revenue, invoice stats, subscription metrics.
All endpoints require merchant auth.

GET /v1/analytics/revenue?period=7d|30d|90d|1y
GET /v1/analytics/invoices?period_days=30
GET /v1/analytics/subscriptions
"""

import logging

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.api.routes.analytics_schemas import (
    InvoiceStatsResponse,
    RevenueResponse,
    SubscriptionMetricsResponse,
)
from app.db.models import Merchant
from app.db.session import get_db
from app.dependencies import get_redis
from app.services.analytics_service import (
    get_invoice_stats,
    get_revenue,
    get_subscription_metrics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/revenue", response_model=RevenueResponse)
async def revenue(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    period: str = Query(default="30d", regex="^(7d|30d|90d|1y)$"),
):
    """Revenue over time (confirmed payments, grouped by day)."""
    return await get_revenue(db, redis, merchant.id, period)


@router.get("/invoices", response_model=InvoiceStatsResponse)
async def invoice_stats(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    period_days: int = Query(default=30, ge=1, le=365),
):
    """Invoice status breakdown over period."""
    return await get_invoice_stats(db, redis, merchant.id, period_days)


@router.get("/subscriptions", response_model=SubscriptionMetricsResponse)
async def subscription_metrics(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Subscription health metrics: counts, MRR, churn, growth."""
    return await get_subscription_metrics(db, redis, merchant.id)
