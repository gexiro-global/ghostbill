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
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

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
            parsed = urlparse(url)
            return parsed.hostname is not None and parsed.hostname.endswith(".onion")
        except Exception:
            return False

    def validate_webhook_url(self, url: str) -> tuple[bool, str | None]:
        """Validate webhook URL against TOR_ONLY policy.

        Returns:
            (valid, error_message) — valid=True if URL is allowed.
        """
        try:
            parsed = urlparse(url)
        except Exception as exc:
            return False, f"Invalid webhook URL: {exc}"

        if parsed.scheme not in ("http", "https"):
            return False, "Webhook URL scheme must be http or https"
        if parsed.username or parsed.password:
            return False, "Webhook URL must not include credentials"
        if not parsed.hostname:
            return False, "Webhook URL host is required"

        is_onion = parsed.hostname.endswith(".onion")
        if self._tor_only and not is_onion:
            return False, "TOR_ONLY mode: only .onion webhook URLs accepted"
        if not is_onion:
            try:
                host_ip = ip_address(parsed.hostname)
            except ValueError:
                host_ip = None
            if host_ip is not None and (
                host_ip.is_private
                or host_ip.is_loopback
                or host_ip.is_link_local
                or host_ip.is_multicast
                or host_ip.is_reserved
                or host_ip.is_unspecified
            ):
                return False, "Webhook URL must not target private, loopback, or reserved IP addresses"
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
            response = await client.post(url, content=content, headers=headers, **kwargs)
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
