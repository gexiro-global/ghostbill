"""Redis sliding window rate limiter + per-merchant rate limiter.

IP-based (sorted set): 6 tiers for unauthenticated/public/Tor requests.
Merchant-based (INCR+EXPIRE, Phase 6C): write 120/min, read 300/min.

Algorithm (sorted set per identifier):
1. ZREMRANGEBYSCORE key 0 (now - window) -> remove expired entries
2. ZCARD key -> current request count
3. If count >= limit -> reject (HTTP 429)
4. ZADD key now now -> record current request
5. EXPIRE key window -> auto-cleanup safety net
"""

import time
import logging
from enum import Enum

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

RATE_LIMIT_KEY_PREFIX = "ratelimit"


class RateTier(str, Enum):
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"
    UNAUTHENTICATED = "unauthenticated"
    TOR_UNAUTHENTICATED = "tor_unauthenticated"
    PUBLIC_API = "public_api"


# Requests per window (window = 60 seconds)
TIER_LIMITS: dict[RateTier, int] = {
    RateTier.STARTER: 100,
    RateTier.GROWTH: 300,
    RateTier.ENTERPRISE: 1000,
    RateTier.UNAUTHENTICATED: 10,
    RateTier.TOR_UNAUTHENTICATED: 30,
    RateTier.PUBLIC_API: 300,
}

WINDOW_SECONDS = 60


class RateLimitResult:
    """Result of a rate limit check."""

    __slots__ = ("allowed", "limit", "remaining", "reset_after", "retry_after")

    def __init__(
        self,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_after: float,
        retry_after: float | None = None,
    ):
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.reset_after = reset_after
        self.retry_after = retry_after

    def headers(self) -> dict[str, str]:
        """Rate limit headers for HTTP response."""
        h = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_after)),
        }
        if self.retry_after is not None:
            h["Retry-After"] = str(int(self.retry_after) + 1)
        return h


class SlidingWindowRateLimiter:
    """Redis-based sliding window rate limiter."""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def check(
        self,
        identifier: str,
        tier: RateTier = RateTier.STARTER,
        window: int = WINDOW_SECONDS,
    ) -> RateLimitResult:
        """Check if request is allowed under rate limit."""
        limit = TIER_LIMITS.get(tier, TIER_LIMITS[RateTier.UNAUTHENTICATED])
        now = time.time()
        window_start = now - window
        redis_key = f"{RATE_LIMIT_KEY_PREFIX}:{tier.value}:{identifier}"

        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            member = f"{now:.6f}"
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, window + 1)
            pipe.zrange(redis_key, 0, 0, withscores=True)

            results = await pipe.execute()
            current_count = results[1]
            oldest_entries = results[4]

            reset_after = window
            if oldest_entries:
                oldest_score = oldest_entries[0][1]
                reset_after = max(0, (oldest_score + window) - now)

            if current_count >= limit:
                await self._redis.zrem(redis_key, member)
                return RateLimitResult(
                    allowed=False, limit=limit, remaining=0,
                    reset_after=reset_after, retry_after=reset_after,
                )

            return RateLimitResult(
                allowed=True, limit=limit,
                remaining=limit - current_count - 1,
                reset_after=reset_after,
            )

        except Exception as e:
            logger.error(f"Rate limiter Redis error: {e}")
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit,
                reset_after=window,
            )

    async def get_usage(self, identifier: str, tier: RateTier) -> int:
        """Get current request count for an identifier."""
        now = time.time()
        redis_key = f"{RATE_LIMIT_KEY_PREFIX}:{tier.value}:{identifier}"
        try:
            await self._redis.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
            return await self._redis.zcard(redis_key)
        except Exception:
            return 0

    async def reset(self, identifier: str, tier: RateTier) -> None:
        """Reset rate limit for an identifier (admin use)."""
        redis_key = f"{RATE_LIMIT_KEY_PREFIX}:{tier.value}:{identifier}"
        try:
            await self._redis.delete(redis_key)
        except Exception as e:
            logger.error(f"Rate limiter reset error: {e}")


# ── Per-Merchant Rate Limiter (Phase 6C) ────────────────────────────

MERCHANT_LIMITS: dict[str, int] = {
    "write": 120,   # POST/PATCH/DELETE/PUT per minute
    "read": 300,    # GET per minute
}


class MerchantRateLimiter:
    """Per-merchant rate limiter using Redis INCR + EXPIRE.

    Simpler than sorted set — sufficient for merchant-level limits.
    """

    def __init__(self, redis: Redis):
        self._redis = redis

    async def check(
        self,
        merchant_id: str,
        tier: str,
    ) -> RateLimitResult:
        """Check if merchant request is allowed.

        Args:
            merchant_id: Merchant UUID string.
            tier: 'write' or 'read'.
        """
        limit = MERCHANT_LIMITS.get(tier, 120)
        key = f"rate:merchant:{merchant_id}:{tier}"

        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.incr(key)
            pipe.ttl(key)
            results = await pipe.execute()
            count = results[0]
            ttl = results[1]

            if ttl == -1:
                await self._redis.expire(key, 60)
                ttl = 60

            remaining = max(0, limit - count)
            allowed = count <= limit
            reset_after = float(ttl) if ttl > 0 else 60.0

            return RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_after=reset_after,
                retry_after=reset_after if not allowed else None,
            )

        except Exception as e:
            logger.error(f"Merchant rate limiter Redis error: {e}")
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit,
                reset_after=60.0,
            )


# ── Helpers ───────────────────────────────────────────────────────────────


def get_identifier_for_key(api_key_hash: str) -> str:
    """Extract rate limit identifier from API key hash."""
    return api_key_hash[:16]


def detect_tor_request(request_ip: str) -> bool:
    """Detect if request comes from Tor."""
    tor_indicators = ("127.0.0.1", "::1", "172.17.", "172.18.", "172.19.")
    return request_ip.startswith(tor_indicators)
