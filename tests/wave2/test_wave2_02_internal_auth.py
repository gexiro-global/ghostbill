import pytest

from app.main import _require_internal_authorization


class Client:
    def __init__(self, host: str):
        self.host = host


class Request:
    def __init__(self, host: str, token: str | None):
        self.client = Client(host)
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}


def test_internal_auth_requires_ip_and_bearer(monkeypatch):
    monkeypatch.setattr("app.main.settings.internal_secret", "test-internal-secret")
    monkeypatch.setattr("app.main.settings.app_env", "production")

    _require_internal_authorization(Request("127.0.0.1", "test-internal-secret"))

    with pytest.raises(Exception) as wrong_bearer:
        _require_internal_authorization(Request("127.0.0.1", "wrong"))
    assert wrong_bearer.value.status_code == 401

    with pytest.raises(Exception) as external:
        _require_internal_authorization(Request("203.0.113.10", "test-internal-secret"))
    assert external.value.status_code == 403

    monkeypatch.setattr("app.main.settings.internal_secret", "")
    with pytest.raises(Exception) as unconfigured:
        _require_internal_authorization(Request("127.0.0.1", "test-internal-secret"))
    assert unconfigured.value.status_code == 503
