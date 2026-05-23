"""Analytics service — aggregate queries with Redis cache.

Phase 7A: Revenue, invoice stats, subscription metrics.
All queries scoped per merchant_id. Cache TTL: 300s (5 min).
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Invoice,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)

PICONERO = Decimal("1000000000000")
CACHE_TTL = 300  # 5 minutes

PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "1y": 365,
}


def _atomic_to_xmr(atomic: int) -> str:
    """Convert piconero to XMR string."""
    d = Decimal(str(atomic)) / PICONERO
    return f"{d:.12f}".rstrip("0").rstrip(".")


async def _cached(redis: Redis, key: str):
    """Return cached JSON or None."""
    raw = await redis.get(key)
    if raw:
        return json.loads(raw)
    return None


async def _set_cache(redis: Redis, key: str, data: dict):
    """Set cache with TTL."""
    await redis.set(key, json.dumps(data), ex=CACHE_TTL)


# ──────────────────────────────────────────────────────────────────────
# Revenue
# ──────────────────────────────────────────────────────────────────────


async def get_revenue(
    db: AsyncSession,
    redis: Redis,
    merchant_id: uuid.UUID,
    period: str = "30d",
) -> dict:
    """Daily revenue (confirmed payments) over period."""
    cache_key = f"analytics:{merchant_id}:revenue:{period}"
    cached = await _cached(redis, cache_key)
    if cached:
        return cached

    days = PERIOD_DAYS.get(period, 30)
    start = datetime.now(timezone.utc) - timedelta(days=days)

    day_col = func.date_trunc("day", func.min(Payment.confirmed_at))

    stmt = (
        select(
            Invoice.id.label("invoice_id"),
            Invoice.amount_atomic.label("invoice_amount_atomic"),
            day_col.label("day"),
            func.count().label("count"),
            func.sum(Payment.amount_atomic).label("gross_received_atomic"),
        )
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(
            Invoice.merchant_id == merchant_id,
            Payment.status == PaymentStatus.confirmed,
            Payment.confirmed_at >= start,
            Payment.confirmed_at.isnot(None),
        )
        .group_by(Invoice.id, Invoice.amount_atomic)
        .order_by(day_col)
    )

    rows = (await db.execute(stmt)).all()

    daily: dict[str, dict] = {}
    grand_gross_received = 0
    grand_invoice_revenue = 0
    grand_count = 0

    for row in rows:
        gross_received_atomic = int(row.gross_received_atomic or 0)
        invoice_revenue_atomic = min(gross_received_atomic, int(row.invoice_amount_atomic or 0))
        date_key = row.day.strftime("%Y-%m-%d")
        point = daily.setdefault(
            date_key,
            {
                "date": date_key,
                "count": 0,
                "gross_received_atomic": 0,
                "gross_received_xmr": _atomic_to_xmr(0),
                "invoice_revenue_atomic": 0,
                "invoice_revenue_xmr": _atomic_to_xmr(0),
                "amount_atomic": 0,
                "amount_xmr": _atomic_to_xmr(0),
            },
        )
        point["count"] += row.count
        point["gross_received_atomic"] += gross_received_atomic
        point["invoice_revenue_atomic"] += invoice_revenue_atomic
        point["amount_atomic"] = point["invoice_revenue_atomic"]
        point["gross_received_xmr"] = _atomic_to_xmr(point["gross_received_atomic"])
        point["invoice_revenue_xmr"] = _atomic_to_xmr(point["invoice_revenue_atomic"])
        point["amount_xmr"] = point["invoice_revenue_xmr"]
        grand_gross_received += gross_received_atomic
        grand_invoice_revenue += invoice_revenue_atomic
        grand_count += row.count

    data = [daily[key] for key in sorted(daily)]

    result = {
        "period": period,
        "data": data,
        "gross_received_atomic": grand_gross_received,
        "gross_received_xmr": _atomic_to_xmr(grand_gross_received),
        "invoice_revenue_atomic": grand_invoice_revenue,
        "invoice_revenue_xmr": _atomic_to_xmr(grand_invoice_revenue),
        "total_atomic": grand_invoice_revenue,
        "total_xmr": _atomic_to_xmr(grand_invoice_revenue),
        "total_payments": grand_count,
    }

    await _set_cache(redis, cache_key, result)
    return result


# ──────────────────────────────────────────────────────────────────────
# Invoice stats
# ──────────────────────────────────────────────────────────────────────


async def get_invoice_stats(
    db: AsyncSession,
    redis: Redis,
    merchant_id: uuid.UUID,
    period_days: int = 30,
) -> dict:
    """Invoice status breakdown."""
    cache_key = f"analytics:{merchant_id}:invoices:{period_days}"
    cached = await _cached(redis, cache_key)
    if cached:
        return cached

    start = datetime.now(timezone.utc) - timedelta(days=period_days)

    stmt = (
        select(
            Invoice.status.label("status"),
            func.count().label("count"),
        )
        .where(
            Invoice.merchant_id == merchant_id,
            Invoice.created_at >= start,
        )
        .group_by(Invoice.status)
    )

    rows = (await db.execute(stmt)).all()

    data = []
    total = 0
    for row in rows:
        count = row.count
        total += count
        data.append({"status": row.status.value, "count": count})

    # Sort: paid first, then by count desc
    status_order = ["paid", "pending", "expired", "partially_paid", "overpaid", "late_paid", "cancelled"]
    data.sort(key=lambda x: status_order.index(x["status"]) if x["status"] in status_order else 99)

    result = {"total": total, "data": data, "period_days": period_days}
    await _set_cache(redis, cache_key, result)
    return result


# ──────────────────────────────────────────────────────────────────────
# Subscription metrics
# ──────────────────────────────────────────────────────────────────────


async def get_subscription_metrics(
    db: AsyncSession,
    redis: Redis,
    merchant_id: uuid.UUID,
) -> dict:
    """Subscription health: counts, MRR, churn, growth."""
    cache_key = f"analytics:{merchant_id}:subscriptions"
    cached = await _cached(redis, cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Status counts
    status_stmt = (
        select(
            Subscription.status.label("status"),
            func.count().label("count"),
        )
        .where(Subscription.merchant_id == merchant_id)
        .group_by(Subscription.status)
    )
    status_rows = (await db.execute(status_stmt)).all()

    counts = {s.value: 0 for s in SubscriptionStatus}
    total = 0
    for row in status_rows:
        counts[row.status.value] = row.count
        total += row.count

    # MRR: sum of (amount_atomic * 30 / interval_days) for active subs
    mrr_stmt = select(func.sum((Subscription.amount_atomic * 30) / Subscription.interval_days).label("mrr")).where(
        Subscription.merchant_id == merchant_id,
        Subscription.status == SubscriptionStatus.active,
    )
    mrr_row = (await db.execute(mrr_stmt)).scalar_one_or_none()
    mrr_atomic = int(mrr_row or 0)

    # Churn (30d): cancelled + expired in last 30 days
    churn_stmt = select(func.count()).where(
        Subscription.merchant_id == merchant_id,
        Subscription.status.in_([SubscriptionStatus.cancelled, SubscriptionStatus.expired]),
        Subscription.updated_at >= thirty_days_ago,
    )
    churn_30d = (await db.execute(churn_stmt)).scalar_one() or 0

    # Net new (30d): created in last 30 days
    new_stmt = select(func.count()).where(
        Subscription.merchant_id == merchant_id,
        Subscription.created_at >= thirty_days_ago,
    )
    new_30d = (await db.execute(new_stmt)).scalar_one() or 0

    result = {
        "active": counts.get("active", 0),
        "paused": counts.get("paused", 0),
        "past_due": counts.get("past_due", 0),
        "cancelled": counts.get("cancelled", 0),
        "expired": counts.get("expired", 0),
        "total": total,
        "mrr_atomic": mrr_atomic,
        "mrr_xmr": _atomic_to_xmr(mrr_atomic),
        "churn_30d": churn_30d,
        "new_30d": new_30d,
    }

    await _set_cache(redis, cache_key, result)
    return result
