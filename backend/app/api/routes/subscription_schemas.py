"""Pydantic schemas for subscription API routes.

Phase 8A: +trial_days in create request, +trial fields in response.
Phase 8B: +PrepayRequest, +prepaid fields in response.
"""

from pydantic import BaseModel, Field, field_validator

MAX_METADATA_KEYS = 20
MAX_METADATA_KEY_LENGTH = 64
MAX_METADATA_STRING_LENGTH = 1024
MAX_METADATA_DEPTH = 2


def validate_metadata_value(value, depth: int = 0) -> None:
    if depth > MAX_METADATA_DEPTH:
        raise ValueError("metadata nesting depth exceeds 2.")
    if isinstance(value, dict):
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError("metadata may contain at most 20 keys.")
        for key, nested in value.items():
            if not isinstance(key, str) or len(key) > MAX_METADATA_KEY_LENGTH:
                raise ValueError("metadata keys must be strings up to 64 characters.")
            validate_metadata_value(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            validate_metadata_value(nested, depth + 1)
    elif isinstance(value, str) and len(value) > MAX_METADATA_STRING_LENGTH:
        raise ValueError("metadata string values must be at most 1024 characters.")


class SubscriptionCreateRequest(BaseModel):
    customer_id: str = Field(..., description="Customer UUID")
    amount_xmr: str = Field(..., description="XMR amount per period", examples=["0.5"])
    interval_days: int = Field(..., ge=1, description="Billing interval in days")
    grace_days_soft: int = Field(default=3, ge=0, description="Days before past_due")
    grace_days_hard: int = Field(default=7, ge=0, description="Days before expired")
    start_at: str | None = Field(default=None, description="ISO datetime, default=now")
    trial_days: int | None = Field(default=None, ge=1, le=365, description="Trial period in days (Phase 8A)")
    metadata: dict | None = Field(default=None, description="Arbitrary metadata")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict | None) -> dict | None:
        if value is not None:
            validate_metadata_value(value)
        return value


class SubscriptionUpdateRequest(BaseModel):
    """Phase 6A: PATCH fields. All optional. None = clear pending change."""

    amount_xmr: str | None = Field(default=None, description="New XMR amount (pending)")
    interval_days: int | None = Field(default=None, description="New interval (pending)")
    grace_days_soft: int | None = Field(default=None, description="New soft grace (pending)")
    grace_days_hard: int | None = Field(default=None, description="New hard grace (pending)")
    metadata: dict | None = Field(default=None, description="Metadata (immediate)")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict | None) -> dict | None:
        if value is not None:
            validate_metadata_value(value)
        return value


class PrepayRequest(BaseModel):
    """Phase 8B: Pre-payment request."""

    periods: int = Field(..., ge=1, le=36, description="Number of periods to prepay (1-36)")


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
    trial_days: int | None = None  # Phase 8A
    trial_end_at: str | None = None  # Phase 8A
    prepaid_until: str | None = None  # Phase 8B
    metadata: dict | None = None
    pending_changes: PendingChangesResponse | None = None
    has_pending_changes: bool = False
    created_at: str
    updated_at: str


class SubscriptionDetailResponse(SubscriptionResponse):
    customer: dict | None = None
    payments: list[dict] = []


class SubscriptionCursorResponse(BaseModel):
    """Phase 6B: cursor pagination response."""

    data: list[SubscriptionResponse]
    has_more: bool


class PrepayResponse(BaseModel):
    """Phase 8B: Pre-payment response with invoice details."""

    subscription_id: str
    invoice_id: str
    periods: int
    discount_pct: int
    per_period_xmr: str
    total_xmr: str
    total_atomic: int
    prepaid_until: str
    invoice_expires_at: str
