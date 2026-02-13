"""
Security headers middleware.

Adds security headers to all HTTP responses:
- Content-Security-Policy (CSP)
- Strict-Transport-Security (HSTS)
- Cross-Origin-Opener-Policy (COOP)
- Cross-Origin-Resource-Policy (CORP)
- Permissions-Policy
- Referrer-Policy
- X-Content-Type-Options
- X-Frame-Options
- Cache-Control (for API responses)
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# CSP: restrictive for API backend (no inline scripts, no external resources)
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'none'",
])

# HSTS: 1 year, include subdomains
STRICT_TRANSPORT_SECURITY = "max-age=31536000; includeSubDomains"

# Permissions-Policy: deny everything (API backend needs none of these)
PERMISSIONS_POLICY = ", ".join([
    "accelerometer=()",
    "camera=()",
    "geolocation=()",
    "gyroscope=()",
    "magnetometer=()",
    "microphone=()",
    "payment=()",
    "usb=()",
    "interest-cohort=()",
])

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Strict-Transport-Security": STRICT_TRANSPORT_SECURITY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": PERMISSIONS_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
    # Remove server identification
    "Server": "GhostBill",
}

# Headers to remove if present
REMOVE_HEADERS = ["X-Powered-By"]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value

        # Remove any accidentally leaked headers
        for header in REMOVE_HEADERS:
            if header in response.headers:
                del response.headers[header]

        return response
