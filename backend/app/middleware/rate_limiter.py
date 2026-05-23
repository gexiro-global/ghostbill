"""Rate limiter middleware.

Wraps core/rate_limit.py into Starlette middleware.
Phase 6C: hybrid IP-based + merchant-based rate limiting.

Flow:
1. Skip exempt paths/IPs
2. IP-based check (existing: sorted set, 6 tiers)
3. If authenticated (Bearer gb_*) → merchant-based check (INCR+EXPIRE)
4. Merchant headers override IP headers in response
"""

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.rate_limit import (
    MerchantRateLimiter,
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

# Proxies allowed to supply X-Forwarded-For. Direct clients are never trusted.
TRUSTED_PROXIES = {"127.0.0.1", "::1", "172.17.0.1", "172.18.0.1", "172.19.0.1", "172.23.0.1"}

# Public API paths — higher rate limit, no auth required
PUBLIC_API_PATTERN = re.compile(
    r"^/v1/invoices/[0-9a-f\-]{36}/public$|^/v1/invoices/[0-9a-f\-]{36}/events$|^/pay/[0-9a-f\-]{36}$",
    re.IGNORECASE,
)

# Methods considered "write" for merchant rate limiting
WRITE_METHODS = {"POST", "PATCH", "DELETE", "PUT"}


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """HTTP middleware for rate limiting API requests."""

    def __init__(self, app, redis=None):
        super().__init__(app)
        self._redis = redis
        self._limiter: SlidingWindowRateLimiter | None = None
        self._merchant_limiter: MerchantRateLimiter | None = None

    def _get_limiter(self, redis) -> SlidingWindowRateLimiter:
        if self._limiter is None:
            self._limiter = SlidingWindowRateLimiter(redis)
        return self._limiter

    def _get_merchant_limiter(self, redis) -> MerchantRateLimiter:
        if self._merchant_limiter is None:
            self._merchant_limiter = MerchantRateLimiter(redis, fail_open=False)
        return self._merchant_limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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

        # ── Layer 1: IP-based rate limit ──────────────────────────
        limiter = self._get_limiter(redis)
        identifier, tier = self._resolve_rate_context(request)
        ip_result = await limiter.check(identifier, tier)

        if not ip_result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Retry after {int(ip_result.retry_after or 60)} seconds.",
                    "retry_after": int(ip_result.retry_after or 60),
                },
                headers=ip_result.headers(),
            )

        # ── Layer 2: Merchant-based rate limit (Phase 6C) ──────────
        response_headers = ip_result.headers()
        # If Bearer auth present, check merchant limit before route execution.
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer gb_"):
            api_key = auth_header[7:]
            merchant_identifier = get_identifier_for_key(api_key)
            merchant_limiter = self._get_merchant_limiter(redis)
            m_tier = "write" if request.method in WRITE_METHODS else "read"
            m_result = await merchant_limiter.check(merchant_identifier, m_tier)

            if not m_result.allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "merchant_rate_limit_exceeded",
                        "message": (
                            f"Merchant rate limit exceeded. Retry after {int(m_result.retry_after or 60)} seconds."
                        ),
                        "retry_after": int(m_result.retry_after or 60),
                    },
                    headers=m_result.headers(),
                )

            response = await call_next(request)
            for h, v in m_result.headers().items():
                response.headers[h] = v
            # Add IP headers too
            for header, value in ip_result.headers().items():
                if header not in response.headers:
                    response.headers[header] = value
            return response

        # Non-authenticated: just IP limit
        response = await call_next(request)
        for header, value in response_headers.items():
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
        """Extract client IP from trusted proxy headers or the direct peer."""
        peer_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and peer_ip in TRUSTED_PROXIES:
            return forwarded.split(",")[0].strip()
        return peer_ip
