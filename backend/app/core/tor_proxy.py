"""
Tor SOCKS5 proxy for outgoing HTTP requests.

Routes all outgoing traffic (webhooks, price feed) through Tor.
Benefits:
    - Merchant webhook endpoints don't see server IP
    - Price feed APIs don't see server IP
    - All outgoing traffic anonymized

Config (.env):
    TOR_PROXY=socks5h://127.0.0.1:9050
    GHOSTBILL_USE_TOR_PROXY=true
    GHOSTBILL_TOR_ONLY=false

If GHOSTBILL_TOR_ONLY=true:
    - Reject non-.onion webhook URLs (400)
    - All outgoing via Tor only
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TorProxy:
    """HTTP client that routes requests through Tor SOCKS5 proxy."""

    def __init__(self) -> None:
        self._proxy_url: str = settings.tor_proxy  # socks5h://127.0.0.1:9050
        self._enabled: bool = settings.use_tor_proxy
        self._tor_only: bool = settings.tor_only

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def tor_only(self) -> bool:
        return self._tor_only

    def is_onion_url(self, url: str) -> bool:
        """Check if URL is a .onion address."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.hostname is not None and parsed.hostname.endswith(".onion")
        except Exception:
            return False

    def validate_webhook_url(self, url: str) -> tuple[bool, str | None]:
        """Validate webhook URL against TOR_ONLY policy.

        Returns:
            (valid, error_message) — valid=True if URL is allowed.
        """
        if self._tor_only and not self.is_onion_url(url):
            return False, "TOR_ONLY mode: only .onion webhook URLs accepted"
        return True, None

    def _get_client_kwargs(self, timeout: float = 15.0) -> dict[str, Any]:
        """Build httpx.AsyncClient kwargs with optional proxy."""
        kwargs: dict[str, Any] = {"timeout": timeout}
        if self._enabled:
            kwargs["proxy"] = self._proxy_url
        return kwargs

    async def post(
        self,
        url: str,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send POST request, optionally via Tor SOCKS5.

        Args:
            url: Target URL.
            content: Raw bytes body.
            headers: HTTP headers.
            timeout: Request timeout in seconds.

        Returns:
            httpx.Response object.
        """
        client_kwargs = self._get_client_kwargs(timeout)
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(
                url, content=content, headers=headers, **kwargs
            )
        if self._enabled:
            logger.debug("POST via Tor: %s -> %d", url, response.status_code)
        return response

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: float = 15.0,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send GET request, optionally via Tor SOCKS5.

        Args:
            url: Target URL.
            params: Query parameters.
            timeout: Request timeout in seconds.

        Returns:
            httpx.Response object.
        """
        client_kwargs = self._get_client_kwargs(timeout)
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(url, params=params, **kwargs)
        if self._enabled:
            logger.debug("GET via Tor: %s -> %d", url, response.status_code)
        return response


# ─── Module-level instance ───────────────────────────────────────────────────

tor_proxy = TorProxy()
