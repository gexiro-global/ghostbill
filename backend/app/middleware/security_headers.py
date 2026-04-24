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

Note: /pay/* and /v1/invoices/*/public paths set their own CSP headers
(allowing inline scripts/styles for the payment page). This middleware
does NOT overwrite CSP or Cache-Control for those paths.
"""

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# CSP: restrictive for API backend (no inline scripts, no external resources)
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ]
)

# HSTS: 1 year, include subdomains
STRICT_TRANSPORT_SECURITY = "max-age=31536000; includeSubDomains"

# Permissions-Policy: deny everything (API backend needs none of these)
PERMISSIONS_POLICY = ", ".join(
    [
        "accelerometer=()",
        "camera=()",
        "geolocation=()",
        "gyroscope=()",
        "magnetometer=()",
        "microphone=()",
        "payment=()",
        "usb=()",
        "interest-cohort=()",
    ]
)

# Headers applied to ALL responses
SECURITY_HEADERS_ALWAYS: dict[str, str] = {
    "Strict-Transport-Security": STRICT_TRANSPORT_SECURITY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": PERMISSIONS_POLICY,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Remove server identification
    "Server": "GhostBill",
}

# Headers applied ONLY to non-public paths (API endpoints)
SECURITY_HEADERS_API_ONLY: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
}

# Headers to remove if present
REMOVE_HEADERS = ["X-Powered-By"]

# Public paths that set their own CSP (allowing inline JS/CSS for payment page)
# These paths manage their own Content-Security-Policy and Cache-Control headers
PUBLIC_PAGE_PATTERN = re.compile(
    r"^/pay/[0-9a-f\-]{36}$|^/v1/invoices/[0-9a-f\-]{36}/public$",
    re.IGNORECASE,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all responses.

    Public payment paths (/pay/*, /v1/invoices/*/public) set their own
    CSP headers with 'unsafe-inline' for script/style. This middleware
    does NOT overwrite those headers for public paths.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Always add base security headers
        for header, value in SECURITY_HEADERS_ALWAYS.items():
            response.headers[header] = value

        # Add restrictive CSP + Cache-Control only for non-public paths
        # Public paths set their own permissive CSP (inline JS/CSS needed)
        path = request.url.path
        if not PUBLIC_PAGE_PATTERN.match(path):
            for header, value in SECURITY_HEADERS_API_ONLY.items():
                response.headers[header] = value

        # Remove any accidentally leaked headers
        for header in REMOVE_HEADERS:
            if header in response.headers:
                del response.headers[header]

        return response
