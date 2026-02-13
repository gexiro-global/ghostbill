"""
Background task: poll XMR price every 60s and store in Redis.

Started in FastAPI lifespan, runs as asyncio task.
Uses PriceFeedService (CoinGecko -> Kraken -> cache fallback).
"""

import asyncio
import logging

from redis.asyncio import Redis

from app.services.price_feed import PriceFeedService

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


async def price_updater_loop(redis: Redis) -> None:
    """Infinite loop: fetch price -> Redis every 60s.

    This coroutine is meant to be wrapped in asyncio.create_task()
    and cancelled on shutdown.
    """
    service = PriceFeedService(redis=redis)

    logger.info("Price updater started (interval: %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            result = await service.update_price()
            source = result.get("source", "unknown")
            usd = result.get("usd")
            stale = result.get("stale", False)

            if usd is not None:
                logger.info(
                    "Price updated: $%.2f (source: %s, stale: %s)",
                    usd,
                    source,
                    stale,
                )
            else:
                logger.warning("Price update returned null (source: %s)", source)

        except Exception:
            logger.exception("Price updater error (will retry next cycle)")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
