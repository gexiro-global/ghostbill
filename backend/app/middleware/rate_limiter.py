"""
Rate limiter middleware.

Wraps core/rate_limit.py SlidingWindowRateLimiter into Starlette middleware.
Determines tier from request context:
- Public API paths (/v1/invoices/*/public, /pay/*): PUBLIC_API tier (300/min per IP)
- Authenticated: tier from merchant record (default: starter)
- Unauthenticated: 10/min per IP (or 30/min if Tor)
- Health endpoint: exempt

On 429: returns JSON error with Retry-After header.
On Redis failure: fail-open (request passes through).
"""

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.rate_limit import (
    RateTier,
    SlidingWindowRateLimiter,
    detect_tor_request,
    get_identifier_for_key,
)

logger = logging.getLogger(__name__)

# Paths exempt from rate limiting
EXEMPT_PATHS = {"/health", "/docs", "/openapi.json"}

# Public API paths — higher rate limit, no auth required
# Matches: /v1/invoices/{uuid}/public and /pay/{uuid}
PUBLIC_API_PATTERN = re.compile(
    r"^/v1/invoices/[0-9a-f\-]{36}/public$|^/pay/[0-9a-f\-]{36}$",
    re.IGNORECASE,
)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """HTTP middleware for rate limiting API requests."""

    def __init__(self, app, redis=None):
        super().__init__(app)
        self._redis = redis
        self._limiter: SlidingWindowRateLimiter | None = None

    def _get_limiter(self, redis) -> SlidingWindowRateLimiter:
        """Lazy-init limiter with Redis connection."""
        if self._limiter is None:
            self._limiter = SlidingWindowRateLimiter(redis)
        return self._limiter

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Get Redis from app state (set during startup)
        redis = getattr(request.app.state, "redis", None) or self._redis
        if redis is None:
            # No Redis available — fail-open
            return await call_next(request)

        limiter = self._get_limiter(redis)

        # Determine identifier and tier
        identifier, tier = self._resolve_rate_context(request)

        # Check rate limit
        result = await limiter.check(identifier, tier)

        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Retry after {int(result.retry_after or 60)} seconds.",
                    "retry_after": int(result.retry_after or 60),
                },
                headers=result.headers(),
            )

        # Proceed with request, add rate limit headers to response
        response = await call_next(request)
        for header, value in result.headers().items():
            response.headers[header] = value

        return response

    def _resolve_rate_context(self, request: Request) -> tuple[str, RateTier]:
        """Determine rate limit identifier and tier from request.

        Priority:
        1. Public API paths → PUBLIC_API tier (300/min per IP)
        2. Authenticated (Bearer gb_*) → merchant tier (default starter)
        3. Unauthenticated → 10/min per IP (30/min if Tor)

        Returns:
            (identifier, tier) tuple.
        """
        path = request.url.path

        # Check for public API paths first (before auth check)
        if PUBLIC_API_PATTERN.match(path):
            client_ip = self._get_client_ip(request)
            return f"pub:{client_ip}", RateTier.PUBLIC_API

        # Check for API key in Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer gb_"):
            # Authenticated request — use key prefix as identifier
            # Extract key from "Bearer gb_live_..." or "Bearer gb_test_..."
            api_key = auth_header[7:]  # Remove "Bearer "
            identifier = get_identifier_for_key(api_key)

            # Tier comes from merchant record (stored in request state by auth)
            # Default to starter if not set
            tier = getattr(request.state, "rate_tier", None)
            if tier and isinstance(tier, RateTier):
                return identifier, tier
            return identifier, RateTier.STARTER

        # Unauthenticated request — use client IP
        client_ip = self._get_client_ip(request)

        if detect_tor_request(client_ip):
            return "tor_shared", RateTier.TOR_UNAUTHENTICATED

        return f"ip:{client_ip}", RateTier.UNAUTHENTICATED

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request.

        Checks X-Forwarded-For (reverse proxy) then falls back to client host.
        Returns 'unknown' if cannot determine (safe for rate limiting).
        """
        # X-Forwarded-For: client, proxy1, proxy2
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        if request.client:
            return request.client.host

        return "unknown"
