"""
Monero signature authentication routes.

POST /v1/auth/nonce   — Request a nonce bound to a Monero address
POST /v1/auth/verify  — Verify signature and get session token
POST /v1/auth/logout  — Revoke session token

These endpoints are PUBLIC (no Bearer auth required).
After verify, the returned gbs_ token works as Bearer token for all other routes.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.monero_auth import (
    SESSION_TTL_SECONDS,
    create_session,
    generate_nonce,
    revoke_session,
    validate_monero_address,
    validate_nonce,
    validate_signature_format,
    verify_monero_signature,
)
from app.db.models import Merchant
from app.db.session import get_db
from app.dependencies import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── Request / Response schemas ──────────────────────────────────────────────


class NonceRequest(BaseModel):
    address: str = Field(
        ...,
        description="Monero primary address (95 chars, starts with 4)",
        min_length=95,
        max_length=95,
    )


class NonceResponse(BaseModel):
    nonce: str
    expires_in: int = Field(default=300, description="Nonce TTL in seconds")


class VerifyRequest(BaseModel):
    address: str = Field(
        ...,
        description="Monero primary address",
        min_length=95,
        max_length=95,
    )
    nonce: str = Field(
        ...,
        description="Nonce from /auth/nonce response",
    )
    signature: str = Field(
        ...,
        description="Signature from monero-wallet-cli 'sign' command",
    )


class VerifyResponse(BaseModel):
    session_token: str
    expires_in: int = Field(description="Session TTL in seconds")
    merchant_id: str


class LogoutRequest(BaseModel):
    session_token: str = Field(
        ...,
        description="Session token (gbs_...) to revoke",
    )


class LogoutResponse(BaseModel):
    revoked: bool


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.post("/nonce", response_model=NonceResponse)
async def request_nonce(
    body: NonceRequest,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """Request a nonce for Monero signature authentication.

    The nonce is bound to the provided Monero address and expires in 5 minutes.
    The address must belong to a registered merchant.
    """
    # Validate address format
    if not validate_monero_address(body.address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Monero address format. Must be 95 chars, starting with 4.",
        )

    # Check that address belongs to a registered, active merchant
    result = await db.execute(
        select(Merchant).where(
            Merchant.monero_address == body.address,
            Merchant.is_active == True,
        )
    )
    merchant = result.scalar_one_or_none()

    if merchant is None:
        # Don't reveal whether address exists — generic error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Address not registered or merchant inactive.",
        )

    # Generate nonce
    nonce = await generate_nonce(redis, body.address)

    return NonceResponse(nonce=nonce, expires_in=300)


@router.post("/verify", response_model=VerifyResponse)
async def verify_signature(
    body: VerifyRequest,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """Verify Monero signature and return a session token.

    Flow:
        1. Validate nonce (exists, not expired, bound to address)
        2. Verify signature via wallet-rpc
        3. Create session token (gbs_<hex64>, 24h TTL)

    The nonce is consumed (single-use) regardless of verification result.
    """
    # Validate address format
    if not validate_monero_address(body.address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Monero address format.",
        )

    # Validate signature format
    if not validate_signature_format(body.signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature format. Expected SigV... from monero-wallet-cli.",
        )

    # Validate and consume nonce (atomic get-and-delete)
    nonce_valid, nonce_error = await validate_nonce(redis, body.nonce, body.address)
    if not nonce_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=nonce_error,
        )

    # Verify signature via wallet-rpc
    sig_valid = await verify_monero_signature(
        address=body.address,
        data=body.nonce,
        signature=body.signature,
    )

    if not sig_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature verification failed.",
        )

    # Lookup merchant by address
    result = await db.execute(
        select(Merchant).where(
            Merchant.monero_address == body.address,
            Merchant.is_active == True,
        )
    )
    merchant = result.scalar_one_or_none()

    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Merchant not found or inactive.",
        )

    # Create session
    session_token = await create_session(redis, str(merchant.id))

    logger.info(
        "Monero signature auth successful for merchant %s",
        merchant.id,
    )

    return VerifyResponse(
        session_token=session_token,
        expires_in=SESSION_TTL_SECONDS,
        merchant_id=str(merchant.id),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    body: LogoutRequest,
    redis: Redis = Depends(get_redis),
):
    """Revoke a session token."""
    revoked = await revoke_session(redis, body.session_token)
    return LogoutResponse(revoked=revoked)
