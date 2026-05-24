from __future__ import annotations

from typing import Any

import ghostbill.errors as errors


def test_full_inheritance_chain() -> None:
    assert issubclass(errors.ConfigurationError, errors.GhostBillError)
    assert issubclass(errors.APIError, errors.GhostBillError)
    assert issubclass(errors.AuthenticationError, errors.APIError)
    assert issubclass(errors.AuthorizationError, errors.APIError)
    assert issubclass(errors.NotFoundError, errors.APIError)
    assert issubclass(errors.ConflictError, errors.APIError)
    assert issubclass(errors.ValidationError, errors.APIError)
    assert issubclass(errors.RateLimitError, errors.APIError)
    assert issubclass(errors.ServerError, errors.APIError)
    assert issubclass(errors.NetworkError, errors.GhostBillError)
    assert issubclass(errors.RequestTimeoutError, errors.GhostBillError)
    assert issubclass(errors.WebhookError, errors.GhostBillError)
    assert issubclass(errors.WebhookSignatureError, errors.WebhookError)
    assert issubclass(errors.WebhookTimestampError, errors.WebhookError)
    assert issubclass(errors.WebhookHeaderError, errors.WebhookError)
    assert issubclass(errors.WebhookPayloadError, errors.WebhookError)


def test_api_error_stores_metadata() -> None:
    exc = errors.APIError("boom", status_code=500, code="INTERNAL", request_id="req_abc")

    assert exc.status_code == 500
    assert exc.code == "INTERNAL"
    assert exc.request_id == "req_abc"
    assert str(exc) == "boom"
    assert exc.message == "boom"
    assert exc.response_headers == {}


def test_api_error_response_headers_are_copied() -> None:
    headers = {"X-Foo": "bar"}
    exc = errors.APIError("boom", response_headers=headers)

    headers["X-Foo"] = "changed"

    assert exc.response_headers == {"X-Foo": "bar"}


def test_rate_limit_carries_retry_after() -> None:
    exc = errors.RateLimitError("slow", retry_after=12.5, status_code=429)

    assert exc.retry_after == 12.5


def test_validation_carries_field_errors() -> None:
    field_errors: list[dict[str, Any]] = [{"field": "amount_xmr", "code": "invalid"}]
    exc = errors.ValidationError("bad", errors=field_errors, status_code=422)

    assert exc.errors == field_errors


def test_validation_errors_default_to_empty_list() -> None:
    assert errors.ValidationError("bad").errors == []


def test_authorization_and_request_timeout_do_not_shadow_stdlib() -> None:
    assert errors.AuthorizationError is not PermissionError
    assert errors.RequestTimeoutError is not TimeoutError
