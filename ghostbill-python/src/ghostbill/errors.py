"""GhostBill SDK exception hierarchy.

AuthorizationError and RequestTimeoutError intentionally avoid shadowing the standard-library PermissionError and
TimeoutError names while preserving the SDK's error semantics.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "APIError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "ConflictError",
    "GhostBillError",
    "NetworkError",
    "NotFoundError",
    "RateLimitError",
    "RequestTimeoutError",
    "ServerError",
    "ValidationError",
    "WebhookError",
    "WebhookHeaderError",
    "WebhookPayloadError",
    "WebhookSignatureError",
    "WebhookTimestampError",
]


class GhostBillError(Exception):
    """Base class for every GhostBill SDK exception."""


class ConfigurationError(GhostBillError):
    """Raised at construction time when SDK configuration is invalid."""


class APIError(GhostBillError):
    """Base class for HTTP 4xx and 5xx responses returned by the GhostBill API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
        response_body: Any = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.response_body = response_body
        self.response_headers = dict(response_headers or {})


class AuthenticationError(APIError):
    """HTTP 401 response raised when API authentication fails."""


class AuthorizationError(APIError):
    """HTTP 403 response raised when authenticated credentials are not allowed to perform the request."""


class NotFoundError(APIError):
    """HTTP 404 response raised when the requested GhostBill resource does not exist."""


class ConflictError(APIError):
    """HTTP 409 response raised when the request conflicts with the current resource state."""


class ValidationError(APIError):
    """HTTP 400 or 422 response raised when request data fails validation."""

    def __init__(
        self,
        message: str,
        *,
        errors: list[dict[str, Any]] | None = None,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
        response_body: Any = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            request_id=request_id,
            response_body=response_body,
            response_headers=response_headers,
        )
        self.errors = list(errors or [])


class RateLimitError(APIError):
    """HTTP 429 response raised when the API asks the client to slow down."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
        response_body: Any = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            request_id=request_id,
            response_body=response_body,
            response_headers=response_headers,
        )
        self.retry_after = retry_after


class ServerError(APIError):
    """HTTP 5xx response raised when the GhostBill server cannot complete the request."""


class NetworkError(GhostBillError):
    """Raised for DNS, connection, or protocol failures before a response is received."""


class RequestTimeoutError(GhostBillError):
    """Raised when a connect, read, or write timeout occurs before a response is received."""


class WebhookError(GhostBillError):
    """Base class for webhook processing errors in the GhostBill SDK."""


class WebhookSignatureError(WebhookError):
    """Raised when a webhook HMAC signature does not match the expected value."""


class WebhookTimestampError(WebhookError):
    """Raised when a webhook timestamp is unparseable or outside the replay window."""


class WebhookHeaderError(WebhookError):
    """Raised when a required webhook header is missing."""


class WebhookPayloadError(WebhookError):
    """Raised when a webhook payload cannot be parsed as JSON or has an unexpected shape."""
