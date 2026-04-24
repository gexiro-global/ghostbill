"""Pydantic schemas for analytics API responses.

Phase 7A: Revenue charts, invoice breakdown, subscription metrics.
"""

from pydantic import BaseModel, Field


# ── Revenue ────────────────────────────────────────────────────────────


class RevenueDayPoint(BaseModel):
    """Single data point for revenue chart."""
    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    count: int = Field(..., description="Number of confirmed payments")
    amount_atomic: int = Field(..., description="Total piconero received")
    amount_xmr: str = Field(..., description="Total XMR received (string)")


class RevenueResponse(BaseModel):
    """Revenue over time for chart rendering."""
    period: str = Field(..., description="Period: 7d, 30d, 90d, 1y")
    data: list[RevenueDayPoint] = Field(default_factory=list)
    total_atomic: int = Field(..., description="Grand total piconero")
    total_xmr: str = Field(..., description="Grand total XMR")
    total_payments: int = Field(..., description="Total confirmed payments")


# ── Invoice Stats ──────────────────────────────────────────────────────


class InvoiceStatusCount(BaseModel):
    status: str
    count: int


class InvoiceStatsResponse(BaseModel):
    """Invoice status breakdown."""
    total: int = Field(..., description="Total invoices in period")
    data: list[InvoiceStatusCount] = Field(default_factory=list)
    period_days: int = Field(..., description="Lookback period in days")


# ── Subscription Metrics ───────────────────────────────────────────────


class SubscriptionMetricsResponse(BaseModel):
    """Subscription health overview."""
    active: int = Field(..., description="Currently active subscriptions")
    paused: int = Field(default=0)
    past_due: int = Field(default=0)
    cancelled: int = Field(default=0)
    expired: int = Field(default=0)
    total: int = Field(..., description="All subscriptions ever")
    mrr_atomic: int = Field(..., description="Monthly Recurring Revenue in piconero")
    mrr_xmr: str = Field(..., description="MRR in XMR")
    churn_30d: int = Field(..., description="Cancelled + expired in last 30 days")
    new_30d: int = Field(..., description="Created in last 30 days")
