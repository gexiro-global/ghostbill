"""
FastAPI dependency: authenticate merchant via Bearer token.

Supports two auth methods (auto-detected by token prefix):
    1. API key: gb_live_<hex> / gb_test_<hex> → bcrypt verify → Merchant
    2. Session token: gbs_<hex64> → Redis lookup → Merchant

Phase 6C: sets request.state.merchant_id for merchant rate limiting.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import parse_bearer_token, verify_api_key
from app.db.models import ApiKey, Merchant
from app.db.session import get_db
from app.dependencies import get_redis

logger = logging.getLogger(__name__)

# How many chars of the API key to use for DB prefix lookup
KEY_PREFIX_LENGTH = 16  # "gb_live_" (8) + 8 hex = very unique

# Session token prefix
SESSION_TOKEN_PREFIX = "gbs_"


async def _auth_via_api_key(
    token: str,
    db: AsyncSession,
) -> Merchant:
    """Authenticate via API key (gb_live_/gb_test_).

    Lookup by prefix → bcrypt verify → load merchant → update last_used_at.
    """
    prefix = token[:KEY_PREFIX_LENGTH]
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.key_prefix == prefix, ApiKey.is_active == True)
    )
    api_keys = result.scalars().all()

    if not api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    matched_key: ApiKey | None = None
    for key in api_keys:
        if verify_api_key(token, key.key_hash):
            matched_key = key
            break

    if matched_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    merchant_result = await db.execute(
        select(Merchant).where(
            Merchant.id == matched_key.merchant_id,
            Merchant.is_active == True,
        )
    )
    merchant = merchant_result.scalar_one_or_none()

    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Merchant account is inactive.",
        )

    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == matched_key.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await db.commit()

    return merchant


async def _auth_via_session(
    token: str,
    db: AsyncSession,
) -> Merchant:
    """Authenticate via session token (gbs_<hex64>).

    Lookup session in Redis → get merchant_id → load merchant.
    """
    from app.core.monero_auth import validate_session

    redis = await get_redis()
    merchant_id_str = await validate_session(redis, token)

    if merchant_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid.",
        )

    try:
        merchant_uuid = uuid.UUID(merchant_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session data.",
        )

    merchant_result = await db.execute(
        select(Merchant).where(
            Merchant.id == merchant_uuid,
            Merchant.is_active == True,
        )
    )
    merchant = merchant_result.scalar_one_or_none()

    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Merchant account is inactive.",
        )

    return merchant


async def get_current_merchant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Merchant:
    """FastAPI dependency: resolve authenticated merchant from Bearer token.

    Auto-detects auth method by token prefix:
        - gb_live_ / gb_test_ → API key auth (bcrypt)
        - gbs_ → Session token auth (Redis)

    Phase 6C: sets request.state.merchant_id for merchant rate limiting.
    """
    authorization = request.headers.get("Authorization")
    token = parse_bearer_token(authorization)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: Bearer <token>",
        )

    if token.startswith(SESSION_TOKEN_PREFIX):
        merchant = await _auth_via_session(token, db)
    else:
        merchant = await _auth_via_api_key(token, db)

    # Phase 6C: expose merchant_id for middleware rate limiting
    request.state.merchant_id = merchant.id

    return merchant
