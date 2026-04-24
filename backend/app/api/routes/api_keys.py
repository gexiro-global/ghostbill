"""API Key management routes — list (cursor), create, revoke.

Endpoints:
    GET    /v1/api-keys       — list all API keys (cursor pagination)
    POST   /v1/api-keys       — create new API key (plaintext returned ONCE)
    DELETE /v1/api-keys/{id}   — revoke (soft delete: is_active=false)

All endpoints require Bearer auth (merchant scope).
Key format: gb_live_<hex32> / gb_test_<hex32>.
Storage: bcrypt hash in DB (cost >= 12).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.api.routes.api_key_schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyCursorResponse,
    ApiKeyResponse,
)
from app.core.security import generate_api_key, hash_api_key
from app.db.models import ApiKey, AuditLog, Merchant
from app.dependencies import get_db
from app.utils.pagination import paginate_cursor, validate_cursor_params

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ─── Helpers ──────────────────────────────────────────────────────────


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


# ─── Routes ───────────────────────────────────────────────────────────


@router.get("", response_model=ApiKeyCursorResponse)
async def list_api_keys(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    starting_after: uuid.UUID | None = Query(default=None),
    ending_before: uuid.UUID | None = Query(default=None),
):
    """List API keys with cursor pagination."""
    validate_cursor_params(starting_after, ending_before)

    base_query = select(ApiKey).where(ApiKey.merchant_id == merchant.id)

    result = await paginate_cursor(
        db=db,
        base_query=base_query,
        model=ApiKey,
        limit=limit,
        starting_after=starting_after,
        ending_before=ending_before,
    )

    return ApiKeyCursorResponse(
        data=[_key_to_response(k) for k in result["data"]],
        has_more=result["has_more"],
    )


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. Plaintext returned ONCE. Max 10 active per merchant."""
    count_stmt = select(func.count(ApiKey.id)).where(ApiKey.merchant_id == merchant.id, ApiKey.is_active == True)
    active_count = (await db.execute(count_stmt)).scalar_one()
    if active_count >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 active API keys per merchant.")

    plaintext_key = generate_api_key(environment=body.environment)
    key_hash = hash_api_key(plaintext_key)
    key_prefix = plaintext_key[:16]

    api_key = ApiKey(
        merchant_id=merchant.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=body.label,
        environment=body.environment,
        is_active=True,
    )
    db.add(api_key)

    audit = AuditLog(
        merchant_id=merchant.id,
        action="api_key.created",
        entity_type="api_key",
        entity_id=api_key.id,
        details={"key_prefix": key_prefix, "environment": body.environment, "label": body.label},
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
    """Revoke (deactivate) an API key. Soft delete."""
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key ID format.")

    api_key = (
        await db.execute(select(ApiKey).where(ApiKey.id == kid, ApiKey.merchant_id == merchant.id))
    ).scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    if not api_key.is_active:
        raise HTTPException(status_code=400, detail="API key is already revoked.")

    remaining = (
        await db.execute(
            select(func.count(ApiKey.id)).where(
                ApiKey.merchant_id == merchant.id, ApiKey.is_active == True, ApiKey.id != kid
            )
        )
    ).scalar_one()
    if remaining == 0:
        raise HTTPException(status_code=400, detail="Cannot revoke the last active API key. Create a new key first.")

    api_key.is_active = False
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
