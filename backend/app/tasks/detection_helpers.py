"""Detection engine helpers — Redis height tracking, model loaders, constants.

Extracted from detection_engine.py in Phase 6C for maintainability.
"""

import logging
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import Invoice, Merchant

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

SCAN_INTERVAL: int = 30  # seconds between regular scans
DEEP_SCAN_INTERVAL: int = 3600  # seconds between deep scans (1 hour)
DEEP_SCAN_BLOCKS: int = 100  # how far back deep scan goes
REORG_BUFFER: int = 10  # Phase 6C: scan N blocks back for safety

REDIS_HEIGHT_KEY: str = "ghostbill:last_scanned_height"
REDIS_LAST_SWEEP_KEY: str = "ghostbill:detection:last_sweep_at"
REDIS_BLOCKS_BEHIND_KEY: str = "ghostbill:detection:blocks_behind"
LEASE_KEY_PREFIX: str = "ghostbill:lease:"


# ── Redis Helpers ────────────────────────────────────────────────────────────


async def _get_redis() -> aioredis.Redis:
    """Get Redis connection. Uses settings.redis_dsn which respects REDIS_PASSWORD."""
    return aioredis.from_url(settings.redis_dsn, decode_responses=True)


async def get_last_scanned_height() -> int:
    """Read last scanned height from Redis."""
    try:
        r = await _get_redis()
        val = await r.get(REDIS_HEIGHT_KEY)
        await r.aclose()
        return int(val) if val else 0
    except Exception:
        logger.warning("Failed to read last_scanned_height from Redis, starting from 0")
        return 0


async def save_last_scanned_height(height: int) -> None:
    """Save last scanned height to Redis."""
    try:
        r = await _get_redis()
        await r.set(REDIS_HEIGHT_KEY, str(height))
        await r.aclose()
    except Exception:
        logger.warning("Failed to save last_scanned_height to Redis")


async def save_health_metrics(current_height: int, last_scanned: int) -> None:
    """Save detection health metrics to Redis (Phase 6C)."""
    from datetime import datetime, timezone

    try:
        r = await _get_redis()
        now_iso = datetime.now(timezone.utc).isoformat()
        blocks_behind = max(0, current_height - last_scanned)
        await r.set(REDIS_LAST_SWEEP_KEY, now_iso)
        await r.set(REDIS_BLOCKS_BEHIND_KEY, str(blocks_behind))
        await r.aclose()
    except Exception:
        logger.warning("Failed to save detection health metrics")


async def acquire_task_lease(task_name: str, ttl_seconds: int, redis_client: Any | None = None) -> bool:
    """Acquire a short Redis lease for one background task iteration.

    Uses SET NX EX so only one process performs a given task iteration. The
    process memory boundary is already trusted for GhostBill secrets; Redis is
    the coordination boundary for multi-worker background tasks.
    """
    r = redis_client or await _get_redis()
    close_client = redis_client is None
    try:
        acquired = await r.set(f"{LEASE_KEY_PREFIX}{task_name}", "1", ex=ttl_seconds, nx=True)
        return bool(acquired)
    except Exception:
        logger.warning("Failed to acquire Redis lease for %s", task_name)
        return False
    finally:
        if close_client:
            try:
                await r.aclose()
            except Exception:
                pass


async def get_health_metrics() -> dict:
    """Read detection health metrics from Redis (for /health endpoint)."""
    try:
        r = await _get_redis()
        height = await r.get(REDIS_HEIGHT_KEY)
        last_sweep = await r.get(REDIS_LAST_SWEEP_KEY)
        blocks_behind = await r.get(REDIS_BLOCKS_BEHIND_KEY)
        await r.aclose()
        return {
            "last_scanned_height": int(height) if height else None,
            "last_sweep_at": last_sweep,
            "blocks_behind": int(blocks_behind) if blocks_behind else None,
        }
    except Exception:
        logger.warning("Failed to read detection health metrics")
        return {"last_scanned_height": None, "last_sweep_at": None, "blocks_behind": None}


# ── Model Loaders ────────────────────────────────────────────────────────────


async def load_merchant(db: AsyncSession, merchant_id) -> Merchant | None:
    """Load merchant by ID."""
    stmt = select(Merchant).where(Merchant.id == merchant_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def load_invoice_with_payments(db: AsyncSession, invoice_id) -> Invoice | None:
    """Load invoice with payments eagerly loaded."""
    stmt = select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.payments))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
