"""Asynchronous GhostBill client.

Resource methods land in later commits; C1 only validates constructor configuration.
"""

from __future__ import annotations

from ._config import _ClientConfig


class AsyncGhostBill:
    """Asynchronous client for the GhostBill payment API."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._config = _ClientConfig(api_key, base_url, timeout, max_retries)

    def __repr__(self) -> str:
        return f"AsyncGhostBill(api_key={self._config.masked_key()!r}, base_url={self._config.base_url!r})"
