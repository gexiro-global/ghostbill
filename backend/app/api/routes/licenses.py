"""License routes — admin CRUD + public verify endpoint.

Admin:
    POST   /v1/admin/licenses          — Create license
    GET    /v1/admin/licenses          — List licenses
    DELETE /v1/admin/licenses/{id}     — Deactivate license

Public:
    GET    /v1/license/verify          — Verify license key (no auth)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.admin import require_admin
from app.db.models import Merchant
from app.db.session import get_db
from app.services.license_service import (
    VALID_TIERS,
    create_license,
    deactivate_license,
    list_licenses,
    verify_license_key,
)

logger = logging.getLogger(__name__)

# ── Routers ─────────────────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/admin/licenses", tags=["admin"])
public_router = APIRouter(prefix="/license", tags=["license"])


# ── Schemas ─────────────────────────────────────────────────────────────────


class CreateLicenseRequest(BaseModel):
    tier: str = Field(..., description="License tier: community, starter, growth, enterprise")
    email: str = Field(..., min_length=5, max_length=255, description="Buyer email")
    duration_days: int | None = Field(None, ge=1, le=3650, description="License duration in days (null = no expiry)")
    note: str | None = Field(None, max_length=500, description="Admin note")


class LicenseResponse(BaseModel):
    id: str
    key_prefix: str
    email: str
    tier: str
    active: bool
    expires_at: str | None
    note: str | None
    created_at: str


class CreateLicenseResponse(BaseModel):
    license: LicenseResponse
    key: str  # Plaintext key — shown ONCE


class VerifyResponse(BaseModel):
    valid: bool
    tier: str | None = None
    expires_at: str | None = None
    limits: dict | None = None
    reason: str | None = None


def _license_to_response(lic) -> LicenseResponse:
    return LicenseResponse(
        id=str(lic.id),
        key_prefix=lic.key_prefix,
        email=lic.email,
        tier=lic.tier,
        active=lic.active,
        expires_at=lic.expires_at.isoformat() if lic.expires_at else None,
        note=lic.note,
        created_at=lic.created_at.isoformat(),
    )


# ── Admin: Create License ───────────────────────────────────────────────


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def create_license_endpoint(
    body: CreateLicenseRequest,
    _admin: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CreateLicenseResponse:
    """Create a new license key. Returns plaintext key ONCE."""
    if body.tier not in VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(VALID_TIERS))}",
        )

    license_obj, plain_key = await create_license(
        db=db,
        tier=body.tier,
        email=body.email,
        duration_days=body.duration_days,
        note=body.note,
    )
    await db.commit()

    return CreateLicenseResponse(
        license=_license_to_response(license_obj),
        key=plain_key,
    )


# ── Admin: List Licenses ────────────────────────────────────────────────


@admin_router.get("")
async def list_licenses_endpoint(
    _admin: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all licenses."""
    licenses = await list_licenses(db)
    return {"licenses": [_license_to_response(lic) for lic in licenses]}


# ── Admin: Deactivate License ──────────────────────────────────────────


@admin_router.delete("/{license_id}")
async def deactivate_license_endpoint(
    license_id: str,
    _admin: Merchant = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Deactivate (soft-delete) a license."""
    license_obj = await deactivate_license(db, license_id)
    if license_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found.")
    await db.commit()
    return {"deactivated": True, "license": _license_to_response(license_obj)}


# ── Public: Verify License ──────────────────────────────────────────────


@public_router.get("/verify")
async def verify_license_endpoint(
    key: str = Query(..., min_length=10, description="License key (gbl_<tier>_<hex>)"),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    """Verify a license key. Public endpoint — no auth required.

    Dashboard calls this on startup to determine feature access.
    """
    result = await verify_license_key(db, key)
    return VerifyResponse(**result)
