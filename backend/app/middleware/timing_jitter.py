"""
Timing jitter middleware.

Adds a random delay (50-200ms) to ALL API responses.
Prevents timing-based side-channel attacks:
- Cannot infer valid vs invalid API keys by response time
- Cannot correlate requests by timing patterns
- Cannot distinguish cache hits from DB queries

Uses asyncio.sleep (non-blocking, doesn't hold threads).
"""

import asyncio
import logging
import random

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

JITTER_MIN_MS = 50
JITTER_MAX_MS = 200


class TimingJitterMiddleware(BaseHTTPMiddleware):
    """Adds random timing jitter to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Skip jitter for health checks (monitoring needs fast responses)
        if request.url.path == "/health":
            return response

        # Random delay between 50-200ms
        delay_ms = random.randint(JITTER_MIN_MS, JITTER_MAX_MS)
        await asyncio.sleep(delay_ms / 1000.0)

        return response
