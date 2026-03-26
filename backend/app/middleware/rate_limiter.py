"""Rate limiter middleware.

Wraps core/rate_limit.py SlidingWindowRateLimiter into Starlette middleware.
Determines tier from request context:
- Internal IPs (127.0.0.1, Docker bridge): exempt
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

# IPs exempt from rate limiting (localhost + Docker bridge gateways)
EXEMPT_IPS = {"127.0.0.1", "::1", "172.17.0.1", "172.23.0.1"}

# Public API paths — higher rate limit, no auth required
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
        if self._limiter is None:
            self._limiter = SlidingWindowRateLimiter(redis)
        return self._limiter

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Skip internal IPs (localhost, Docker bridge)
        client_ip = self._get_client_ip(request)
        if client_ip in EXEMPT_IPS:
            return await call_next(request)

        # Get Redis from app state
        redis = getattr(request.app.state, "redis", None) or self._redis
        if redis is None:
            return await call_next(request)

        limiter = self._get_limiter(redis)
        identifier, tier = self._resolve_rate_context(request)
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

        response = await call_next(request)
        for header, value in result.headers().items():
            response.headers[header] = value
        return response

    def _resolve_rate_context(self, request: Request) -> tuple[str, RateTier]:
        """Determine rate limit identifier and tier from request."""
        path = request.url.path

        if PUBLIC_API_PATTERN.match(path):
            client_ip = self._get_client_ip(request)
            return f"pub:{client_ip}", RateTier.PUBLIC_API

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer gb_"):
            api_key = auth_header[7:]
            identifier = get_identifier_for_key(api_key)
            tier = getattr(request.state, "rate_tier", None)
            if tier and isinstance(tier, RateTier):
                return identifier, tier
            return identifier, RateTier.STARTER

        client_ip = self._get_client_ip(request)
        if detect_tor_request(client_ip):
            return "tor_shared", RateTier.TOR_UNAUTHENTICATED

        return f"ip:{client_ip}", RateTier.UNAUTHENTICATED

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
