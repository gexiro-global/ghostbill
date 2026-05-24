"""Internal shared client configuration.

This module is not part of the public API. It exists so the sync and async clients can share environment fallback and
configuration validation logic without duplicating it.
"""

from __future__ import annotations

import os

from .errors import ConfigurationError

_API_KEY_ENV = "GHOSTBILL_API_KEY"
_BASE_URL_ENV = "GHOSTBILL_BASE_URL"
_KEY_REPR_PREFIX_LEN = 8


class _ClientConfig:
    __slots__ = ("api_key", "base_url", "timeout", "max_retries")

    def __init__(self, api_key: str | None, base_url: str | None, timeout: float, max_retries: int) -> None:
        resolved_api_key = api_key or os.environ.get(_API_KEY_ENV)
        if not resolved_api_key:
            raise ConfigurationError(f"api_key is required or must be set in {_API_KEY_ENV}.")

        resolved_base_url = base_url or os.environ.get(_BASE_URL_ENV)
        if not resolved_base_url:
            raise ConfigurationError(f"base_url is required or must be set in {_BASE_URL_ENV}.")

        if timeout <= 0:
            raise ConfigurationError("timeout must be a positive number.")

        if max_retries < 0:
            raise ConfigurationError("max_retries must be zero or greater.")

        self.api_key = resolved_api_key
        self.base_url = resolved_base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def masked_key(self) -> str:
        if len(self.api_key) >= _KEY_REPR_PREFIX_LEN:
            return f"{self.api_key[:_KEY_REPR_PREFIX_LEN]}..."
        return "***"
