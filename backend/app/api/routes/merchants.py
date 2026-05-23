"""
Merchant API routes.

POST /v1/merchants       — Register new merchant (public, no auth)
GET  /v1/merchants/me    — Get current merchant (auth required)
PATCH /v1/merchants/me   — Update current merchant (auth required)
POST /v1/merchants/me/webhook-secret — Regenerate webhook secret (auth required)
"""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import KEY_PREFIX_LENGTH, get_current_merchant
from app.core.audit import AuditEvent, audit_log_fire
from app.core.encryption import encrypt_view_key
from app.core.security import (
    generate_api_key,
    generate_webhook_secret,
    hash_api_key,
)
from app.db.models import ApiKey, Merchant
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/merchants", tags=["merchants"])

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ─── Request / Response schemas ──────────────────────────────────────────────────


class MerchantRegisterRequest(BaseModel):
    """Registration request. Requires Monero primary address."""

    primary_address: str = Field(
        ...,
        min_length=95,
        max_length=106,
        description="Monero primary address (starts with 4)",
    )
    view_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="Monero secret view key (64 hex chars)",
    )
    name: str = Field(
        default="My Store",
        max_length=255,
        description="Merchant display name",
    )
    email: str | None = Field(
        default=None,
        max_length=255,
        description="Contact email (optional)",
    )
    webhook_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Webhook delivery URL (optional, can set later)",
    )

    @field_validator("primary_address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        if not v.startswith("4"):
            raise ValueError("Monero primary address must start with '4'")
        return v

    @field_validator("view_key")
    @classmethod
    def validate_view_key(cls, v: str) -> str:
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("View key must be a 64-character hex string")
        return v.lower()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is not None and not EMAIL_PATTERN.match(v):
            raise ValueError("Invalid email format.")
        return v


class MerchantRegisterResponse(BaseModel):
    merchant_id: str
    name: str
    environment: str
    api_keys: dict[str, str]
    webhook_secret: str
    message: str = "Store your API keys securely. They will NOT be shown again."


class MerchantMeResponse(BaseModel):
    id: str
    name: str
    email: str | None
    monero_address: str
    webhook_url: str | None
    prepay_plans: list[dict] | None = None  # Phase 8B
    environment: str
    is_active: bool
    created_at: str
    updated_at: str


class MerchantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    webhook_url: str | None = Field(default=None, max_length=2048)
    prepay_plans: list[dict] | None = Field(
        default=None,
        description="Prepay plan configs: [{periods: 3, discount_pct: 10}, ...]",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is not None and not EMAIL_PATTERN.match(v):
            raise ValueError("Invalid email format.")
        return v


class MerchantUpdateResponse(BaseModel):
    id: str
    name: str
    email: str | None
    webhook_url: str | None
    prepay_plans: list[dict] | None = None  # Phase 8B
    updated_at: str
    message: str = "Merchant updated successfully."


class WebhookSecretResponse(BaseModel):
    webhook_secret: str
    message: str = "New webhook secret generated. Update your integration."


# ─── Helpers ────────────────────────────────────────────────────────────────────


def _validate_prepay_plans(plans: list[dict]) -> list[dict]:
    """Validate prepay_plans structure: [{periods: int, discount_pct: int}]."""
    if not isinstance(plans, list):
        raise ValueError("prepay_plans must be a list.")
    if len(plans) > 10:
        raise ValueError("Maximum 10 prepay plans allowed.")
    seen_periods = set()
    validated = []
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError("Each plan must be a dict with 'periods' and 'discount_pct'.")
        periods = plan.get("periods")
        discount_pct = plan.get("discount_pct", 0)
        if not isinstance(periods, int) or periods < 1 or periods > 36:
            raise ValueError(f"periods must be int 1-36, got: {periods}")
        if not isinstance(discount_pct, (int, float)) or discount_pct < 0 or discount_pct > 99:
            raise ValueError(f"discount_pct must be 0-99, got: {discount_pct}")
        if periods in seen_periods:
            raise ValueError(f"Duplicate periods value: {periods}")
        seen_periods.add(periods)
        validated.append({"periods": periods, "discount_pct": int(discount_pct)})
    return validated


# ─── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=MerchantRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_merchant(
    body: MerchantRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new merchant. Returns live + test API keys (shown ONCE)."""

    # Check for duplicate address
    existing = await db.execute(select(Merchant).where(Merchant.monero_address == body.primary_address))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A merchant with this Monero address already exists.",
        )

    # Encrypt view key with AES-256-GCM before storing
    encrypted_view_key = encrypt_view_key(body.view_key)

    # Generate webhook secret
    webhook_secret = generate_webhook_secret()

    # Create merchant
    merchant = Merchant(
        name=body.name,
        email=body.email,
        monero_address=body.primary_address,
        view_key_encrypted=encrypted_view_key,
        webhook_url=body.webhook_url,
        webhook_secret=webhook_secret,
        environment="live",
        is_active=True,
    )
    db.add(merchant)
    await db.flush()  # Get merchant.id before creating keys

    # Generate API keys (live + test)
    plain_keys: dict[str, str] = {}
    for env in ("live", "test"):
        plain_key = generate_api_key(environment=env)
        key_hash = hash_api_key(plain_key)

        api_key = ApiKey(
            merchant_id=merchant.id,
            key_hash=key_hash,
            key_prefix=plain_key[:KEY_PREFIX_LENGTH],
            label=f"Default {env} key",
            environment=env,
            is_active=True,
        )
        db.add(api_key)
        plain_keys[env] = plain_key

    await db.commit()

    logger.info("Merchant registered: %s (%s)", merchant.id, body.name)

    # Audit log (fire-and-forget, never blocks response)
    audit_log_fire(
        db,
        AuditEvent.MERCHANT_REGISTERED,
        merchant.id,
        {"name": body.name, "address": body.primary_address},
    )

    return MerchantRegisterResponse(
        merchant_id=str(merchant.id),
        name=merchant.name,
        environment=merchant.environment,
        api_keys=plain_keys,
        webhook_secret=webhook_secret,
    )


@router.get("/me", response_model=MerchantMeResponse)
async def get_me(
    merchant: Merchant = Depends(get_current_merchant),
):
    """Get current authenticated merchant profile."""
    return MerchantMeResponse(
        id=str(merchant.id),
        name=merchant.name,
        email=merchant.email,
        monero_address=merchant.monero_address,
        webhook_url=merchant.webhook_url,
        prepay_plans=merchant.prepay_plans,
        environment=merchant.environment,
        is_active=merchant.is_active,
        created_at=merchant.created_at.isoformat(),
        updated_at=merchant.updated_at.isoformat(),
    )


@router.patch("/me", response_model=MerchantUpdateResponse)
async def update_me(
    body: MerchantUpdateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Update current merchant profile (name, email, webhook_url, prepay_plans)."""

    # Track which fields changed for audit
    changed_fields = []

    if body.name is not None:
        merchant.name = body.name
        changed_fields.append("name")
    if body.email is not None:
        merchant.email = body.email
        changed_fields.append("email")
    if body.webhook_url is not None:
        merchant.webhook_url = body.webhook_url
        changed_fields.append("webhook_url")
    # Phase 8B: prepay plans
    if body.prepay_plans is not None:
        try:
            merchant.prepay_plans = _validate_prepay_plans(body.prepay_plans)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid prepay_plans: {exc}",
            )
        changed_fields.append("prepay_plans")

    if not changed_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    merchant.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(merchant)

    logger.info("Merchant updated: %s", merchant.id)

    # Audit log
    audit_log_fire(
        db,
        AuditEvent.MERCHANT_UPDATED,
        merchant.id,
        {"fields_changed": changed_fields},
    )

    return MerchantUpdateResponse(
        id=str(merchant.id),
        name=merchant.name,
        email=merchant.email,
        webhook_url=merchant.webhook_url,
        prepay_plans=merchant.prepay_plans,
        updated_at=merchant.updated_at.isoformat(),
    )


@router.post("/me/webhook-secret", response_model=WebhookSecretResponse)
async def regenerate_webhook_secret(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate webhook signing secret."""
    new_secret = generate_webhook_secret()
    merchant.webhook_secret = new_secret
    merchant.updated_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("Webhook secret regenerated: %s", merchant.id)

    return WebhookSecretResponse(webhook_secret=new_secret)
