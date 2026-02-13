"""
XMR price feed service.

Primary: CoinGecko (free API, no key needed)
Fallback: Kraken public ticker
Cache: Redis key "xmr_price", TTL 90s
Stale: price older than 10 minutes

Background task polls every 60s -> Redis.
GET /v1/price reads from Redis only (no external call on request).

Outgoing requests routed via Tor SOCKS5 proxy (if enabled).
"""

import json
import logging
import time
from typing import Any

from redis.asyncio import Redis

from app.core.tor_proxy import tor_proxy

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

REDIS_KEY = "xmr_price"
CACHE_TTL_SECONDS = 90
STALE_THRESHOLD_SECONDS = 600  # 10 minutes

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_PARAMS = {
    "ids": "monero",
    "vs_currencies": "usd,eur",
}

KRAKEN_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_PARAMS = {
    "pair": "XMRUSD,XMREUR",
}

HTTP_TIMEOUT = 10.0  # seconds


# ─── Price Feed Service ─────────────────────────────────────────────────────


class PriceFeedService:
    """Fetch and cache XMR price from external APIs."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_cached_price(self) -> dict[str, Any] | None:
        """Read price from Redis cache.

        Returns:
            Price dict or None if no cache exists.
            Includes "stale": True if older than 10 minutes.
        """
        raw = await self._redis.get(REDIS_KEY)
        if raw is None:
            return None

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

        # Check staleness
        cached_ts = data.get("timestamp_unix", 0)
        age = time.time() - cached_ts
        data["stale"] = age > STALE_THRESHOLD_SECONDS

        return data

    async def update_price(self) -> dict[str, Any]:
        """Fetch fresh price and store in Redis.

        Priority: CoinGecko -> Kraken -> last cached value.
        All outgoing requests routed via Tor proxy (if enabled).

        Returns:
            Price dict with usd, eur, timestamp, source, stale.
        """
        # Try CoinGecko first
        price_data = await self._fetch_coingecko()

        # Fallback to Kraken
        if price_data is None:
            price_data = await self._fetch_kraken()

        # If both failed, return last cached (marked stale)
        if price_data is None:
            cached = await self.get_cached_price()
            if cached is not None:
                cached["stale"] = True
                cached["source"] = "cache"
                return cached
            # No data at all
            return {
                "usd": None,
                "eur": None,
                "timestamp": None,
                "timestamp_unix": 0,
                "source": "none",
                "stale": True,
            }

        # Store in Redis
        await self._redis.setex(
            REDIS_KEY,
            CACHE_TTL_SECONDS,
            json.dumps(price_data),
        )

        price_data["stale"] = False
        return price_data

    async def _fetch_coingecko(self) -> dict[str, Any] | None:
        """Fetch XMR price from CoinGecko free API via Tor proxy."""
        try:
            response = await tor_proxy.get(
                COINGECKO_URL,
                params=COINGECKO_PARAMS,
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            monero = data.get("monero", {})
            usd = monero.get("usd")
            eur = monero.get("eur")

            if usd is None:
                logger.warning("CoinGecko: missing USD price in response")
                return None

            now = time.time()
            return {
                "usd": float(usd),
                "eur": float(eur) if eur is not None else None,
                "timestamp": self._iso_now(),
                "timestamp_unix": now,
                "source": "coingecko",
            }

        except Exception as exc:
            logger.warning("CoinGecko fetch failed: %s", exc)
            return None

    async def _fetch_kraken(self) -> dict[str, Any] | None:
        """Fetch XMR price from Kraken public ticker via Tor proxy (fallback)."""
        try:
            response = await tor_proxy.get(
                KRAKEN_URL,
                params=KRAKEN_PARAMS,
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("error"):
                logger.warning("Kraken API error: %s", data["error"])
                return None

            result = data.get("result", {})

            # Kraken uses XXMRZUSD / XXMRZEUR as pair names
            usd_pair = result.get("XXMRZUSD", {})
            eur_pair = result.get("XXMRZEUR", {})

            # "c" = last trade close price, first element is price string
            usd_price = usd_pair.get("c", [None])[0]
            eur_price = eur_pair.get("c", [None])[0]

            if usd_price is None:
                logger.warning("Kraken: missing USD price in response")
                return None

            now = time.time()
            return {
                "usd": float(usd_price),
                "eur": float(eur_price) if eur_price is not None else None,
                "timestamp": self._iso_now(),
                "timestamp_unix": now,
                "source": "kraken",
            }

        except Exception as exc:
            logger.warning("Kraken fetch failed: %s", exc)
            return None

    @staticmethod
    def _iso_now() -> str:
        """Return current UTC time as ISO string."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
