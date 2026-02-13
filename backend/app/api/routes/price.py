"""
Price API route.

GET /v1/price — Return cached XMR price (no external call on request).
"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.dependencies import get_redis
from app.services.price_feed import PriceFeedService

router = APIRouter(prefix="/price", tags=["price"])


@router.get("")
async def get_price(
    redis: Redis = Depends(get_redis),
):
    """Get current XMR price (USD + EUR).

    Reads from Redis cache only. Background task updates every 60s.
    Returns stale: true if price is older than 10 minutes.

    No authentication required — price is public data.
    """
    service = PriceFeedService(redis=redis)
    cached = await service.get_cached_price()

    if cached is not None:
        # Remove internal field from response
        cached.pop("timestamp_unix", None)
        return cached

    # No cache at all (first startup, before background task runs)
    return {
        "usd": None,
        "eur": None,
        "timestamp": None,
        "source": "none",
        "stale": True,
        "message": "Price not yet available. Background updater is starting.",
    }
