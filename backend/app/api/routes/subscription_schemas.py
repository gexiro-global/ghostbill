"""Pydantic schemas for subscription API routes."""

from pydantic import BaseModel, Field


class SubscriptionCreateRequest(BaseModel):
    customer_id: str = Field(..., description="Customer UUID")
    amount_xmr: str = Field(..., description="XMR amount per period", examples=["0.5"])
    interval_days: int = Field(..., ge=1, description="Billing interval in days")
    grace_days_soft: int = Field(default=3, ge=0, description="Days before past_due")
    grace_days_hard: int = Field(default=7, ge=0, description="Days before expired")
    start_at: str | None = Field(default=None, description="ISO datetime, default=now")
    metadata: dict | None = Field(default=None, description="Arbitrary metadata")


class SubscriptionUpdateRequest(BaseModel):
    """Phase 6A: PATCH fields. All optional. None = clear pending change."""
    amount_xmr: str | None = Field(default=None, description="New XMR amount (pending)")
    interval_days: int | None = Field(default=None, description="New interval (pending)")
    grace_days_soft: int | None = Field(default=None, description="New soft grace (pending)")
    grace_days_hard: int | None = Field(default=None, description="New hard grace (pending)")
    metadata: dict | None = Field(default=None, description="Metadata (immediate)")


class PendingChangesResponse(BaseModel):
    amount_xmr: str | None = None
    amount_atomic: int | None = None
    interval_days: int | None = None
    grace_days_soft: int | None = None
    grace_days_hard: int | None = None


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
    billing_anchor_at: str | None = None
    next_due_at: str | None = None
    cancelled_at: str | None = None
    metadata: dict | None = None
    pending_changes: PendingChangesResponse | None = None
    has_pending_changes: bool = False
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
