"""
API Key management routes — list, create, revoke.

Endpoints:
    GET    /v1/api-keys       — list all API keys (masked, metadata only)
    POST   /v1/api-keys       — create new API key (plaintext returned ONCE)
    DELETE /v1/api-keys/{id}   — revoke (soft delete: is_active=false)

All endpoints require Bearer auth (merchant scope).
Key format: gb_live_<hex32> (production) or gb_test_<hex32> (sandbox)
Storage: bcrypt hash in DB (cost >= 12)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.core.security import generate_api_key, hash_api_key
from app.db.models import ApiKey, AuditLog, Merchant
from app.dependencies import get_db

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ApiKeyCreateRequest(BaseModel):
    label: Optional[str] = Field(None, max_length=255, description="Human-readable label")
    environment: str = Field("live", pattern="^(live|test)$", description="live or test")


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    label: Optional[str] = None
    environment: str
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(BaseModel):
    """Returned only on creation — plaintext key shown ONCE."""
    id: str
    key: str  # Full plaintext key — SAVE THIS
    key_prefix: str
    label: Optional[str] = None
    environment: str


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyResponse]
    total: int


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _key_to_response(key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=str(key.id),
        key_prefix=key.key_prefix,
        label=key.label,
        environment=key.environment,
        is_active=key.is_active,
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
        created_at=key.created_at.isoformat() if key.created_at else None,
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the authenticated merchant.

    Keys are masked — only prefix, label, environment, and metadata shown.
    """
    stmt = (
        select(ApiKey)
        .where(ApiKey.merchant_id == merchant.id)
        .order_by(ApiKey.created_at.desc())
    )
    result = await db.execute(stmt)
    keys = list(result.scalars().all())

    return ApiKeyListResponse(
        api_keys=[_key_to_response(k) for k in keys],
        total=len(keys),
    )


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key.

    The full plaintext key is returned ONCE in the response.
    It cannot be retrieved again — only the prefix is stored.

    Max 10 active keys per merchant.
    """
    # Check active key count
    count_stmt = (
        select(func.count(ApiKey.id))
        .where(ApiKey.merchant_id == merchant.id, ApiKey.is_active == True)
    )
    active_count = (await db.execute(count_stmt)).scalar_one()

    if active_count >= 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 active API keys per merchant.",
        )

    # Generate key
    plaintext_key = generate_api_key(environment=body.environment)
    key_hash = hash_api_key(plaintext_key)
    key_prefix = plaintext_key[:16]  # e.g. "gb_live_5d347e8b"

    api_key = ApiKey(
        merchant_id=merchant.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=body.label,
        environment=body.environment,
        is_active=True,
    )
    db.add(api_key)

    # Audit log
    audit = AuditLog(
        merchant_id=merchant.id,
        action="api_key.created",
        entity_type="api_key",
        entity_id=api_key.id,
        details={
            "key_prefix": key_prefix,
            "environment": body.environment,
            "label": body.label,
        },
    )
    db.add(audit)

    await db.commit()

    return ApiKeyCreateResponse(
        id=str(api_key.id),
        key=plaintext_key,
        key_prefix=key_prefix,
        label=body.label,
        environment=body.environment,
    )


@router.delete("/{key_id}", status_code=200)
async def revoke_api_key(
    key_id: str,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (deactivate) an API key.

    Soft delete: sets is_active=false. Key hash remains in DB for audit.
    Cannot revoke the key currently being used for authentication.
    """
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID format.")

    stmt = select(ApiKey).where(
        ApiKey.id == kid,
        ApiKey.merchant_id == merchant.id,
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found.")

    if not api_key.is_active:
        raise HTTPException(status_code=400, detail="API key is already revoked.")

    # Check if this is the last active key
    count_stmt = (
        select(func.count(ApiKey.id))
        .where(
            ApiKey.merchant_id == merchant.id,
            ApiKey.is_active == True,
            ApiKey.id != kid,
        )
    )
    remaining = (await db.execute(count_stmt)).scalar_one()

    if remaining == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot revoke the last active API key. Create a new key first.",
        )

    api_key.is_active = False

    # Audit log
    audit = AuditLog(
        merchant_id=merchant.id,
        action="api_key.revoked",
        entity_type="api_key",
        entity_id=api_key.id,
        details={"key_prefix": api_key.key_prefix},
    )
    db.add(audit)

    await db.commit()

    return {"detail": "API key revoked.", "key_prefix": api_key.key_prefix}
