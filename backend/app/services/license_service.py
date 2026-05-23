"""License service — generate, hash, verify, CRUD for dashboard license keys.

Key format: gbl_<tier>_<hex32>
Storage: SHA-256 hash (direct DB lookup, no iteration).
Tiers: community, starter, growth, enterprise.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Invoice, License

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_TIERS = {"community", "starter", "growth", "enterprise"}

TIER_LIMITS: dict[str, dict] = {
    "community": {"invoices_per_month": -1, "analytics": False, "admin": False},
    "starter": {"invoices_per_month": 500, "analytics": False, "admin": False},
    "growth": {"invoices_per_month": -1, "analytics": True, "admin": True},
    "enterprise": {"invoices_per_month": -1, "analytics": True, "admin": True},
}

LICENSE_KEY_HEX_LENGTH = 32  # 32 hex chars = 16 bytes entropy


@dataclass(frozen=True)
class TierCheckResult:
    allowed: bool
    over_limit: bool
    tier: str
    limit: int
    current: int


def tier_limit_headers(result: TierCheckResult) -> dict[str, str]:
    """Return response headers that surface soft tier limit state."""
    headers = {"X-License-Tier": result.tier}
    if result.over_limit:
        headers["X-License-Limit-Warning"] = f"{result.current}/{result.limit} {result.tier} limit exceeded"
    return headers


async def check_tier_limit(db: AsyncSession, merchant_id, feature: str) -> TierCheckResult:
    """Soft-check merchant tier limits without blocking operations."""
    tier = "community"
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["community"])
    limit = int(limits.get(feature, -1))
    current = 0

    if feature == "invoices_per_month":
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current = (
            await db.execute(
                select(func.count(Invoice.id)).where(
                    Invoice.merchant_id == merchant_id,
                    Invoice.created_at >= month_start,
                )
            )
        ).scalar_one()

    over_limit = limit >= 0 and current >= limit
    if over_limit:
        logger.warning(
            "LICENSE_TIER_LIMIT_SOFT merchant_id=%s tier=%s feature=%s current=%s limit=%s",
            merchant_id,
            tier,
            feature,
            current,
            limit,
        )

    # TODO: DEC-05 hard enforcement — change allowed to False when over_limit.
    return TierCheckResult(allowed=True, over_limit=over_limit, tier=tier, limit=limit, current=current)


# ── Key Generation ──────────────────────────────────────────────────────────


def generate_license_key(tier: str) -> str:
    """Generate a license key: gbl_<tier>_<hex32>."""
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}. Must be one of {VALID_TIERS}")
    random_hex = secrets.token_hex(LICENSE_KEY_HEX_LENGTH // 2)
    return f"gbl_{tier}_{random_hex}"


def hash_license_key(plain_key: str) -> str:
    """SHA-256 hash of the license key for DB storage."""
    return hashlib.sha256(plain_key.encode("utf-8")).hexdigest()


def extract_key_prefix(plain_key: str) -> str:
    """Extract prefix for admin identification: gbl_<tier>_<first8hex>."""
    parts = plain_key.split("_", maxsplit=2)
    if len(parts) == 3:
        return f"{parts[0]}_{parts[1]}_{parts[2][:8]}"
    return plain_key[:20]


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_license(
    db: AsyncSession,
    tier: str,
    email: str,
    duration_days: int | None = None,
    note: str | None = None,
) -> tuple[License, str]:
    """Create a new license. Returns (License, plaintext_key).

    plaintext_key is shown ONCE to admin, never stored.
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}")

    plain_key = generate_license_key(tier)
    key_hash = hash_license_key(plain_key)
    key_prefix = extract_key_prefix(plain_key)

    expires_at = None
    if duration_days and duration_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

    license_obj = License(
        key_hash=key_hash,
        key_prefix=key_prefix,
        email=email,
        tier=tier,
        active=True,
        expires_at=expires_at,
        note=note,
    )
    db.add(license_obj)
    await db.flush()

    logger.info("License created: tier=%s email=%s prefix=%s", tier, email, key_prefix)
    return license_obj, plain_key


async def list_licenses(db: AsyncSession) -> list[License]:
    """List all licenses ordered by creation date (newest first)."""
    stmt = select(License).order_by(License.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def deactivate_license(db: AsyncSession, license_id: str) -> License | None:
    """Soft-deactivate a license by ID. Returns updated License or None."""
    import uuid as uuid_mod

    try:
        lid = uuid_mod.UUID(license_id)
    except ValueError:
        return None

    stmt = select(License).where(License.id == lid)
    result = await db.execute(stmt)
    license_obj = result.scalar_one_or_none()
    if license_obj is None:
        return None

    license_obj.active = False
    await db.flush()
    logger.info("License deactivated: id=%s prefix=%s", license_id, license_obj.key_prefix)
    return license_obj


async def verify_license_key(db: AsyncSession, plain_key: str) -> dict:
    """Verify a license key. Returns verify response dict.

    Public endpoint — no auth required. Dashboard calls this on startup.
    """
    if not plain_key or not plain_key.startswith("gbl_"):
        return {"valid": False}

    key_hash = hash_license_key(plain_key)
    stmt = select(License).where(License.key_hash == key_hash)
    result = await db.execute(stmt)
    license_obj = result.scalar_one_or_none()

    if license_obj is None:
        return {"valid": False}

    if not license_obj.active:
        return {"valid": False}

    now = datetime.now(timezone.utc)
    if license_obj.expires_at and license_obj.expires_at < now:
        return {"valid": False, "reason": "expired"}

    tier = license_obj.tier
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["community"])

    return {
        "valid": True,
        "tier": tier,
        "expires_at": license_obj.expires_at.isoformat() if license_obj.expires_at else None,
        "limits": limits,
    }
