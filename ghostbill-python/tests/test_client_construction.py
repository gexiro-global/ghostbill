from __future__ import annotations

import pytest

from ghostbill import AsyncGhostBill, GhostBill
from ghostbill.errors import ConfigurationError

API_KEY = "gb_test_xxxxxxxxxxxxxxxxxxxxxxxxxx"
BASE_URL = "https://your-ghostbill.example"


def test_sync_requires_api_key() -> None:
    with pytest.raises(ConfigurationError):
        GhostBill(base_url=BASE_URL)


def test_sync_requires_base_url() -> None:
    with pytest.raises(ConfigurationError):
        GhostBill(api_key=API_KEY)


def test_sync_uses_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHOSTBILL_API_KEY", API_KEY)
    monkeypatch.setenv("GHOSTBILL_BASE_URL", BASE_URL)

    client = GhostBill()

    assert "gb_test_..." in repr(client)
    assert BASE_URL in repr(client)


def test_sync_repr_masks_key() -> None:
    client = GhostBill("gb_test_xxxxxxxxxxxxxxxxxxxxxxx", base_url=BASE_URL)

    assert "gb_test_..." in repr(client)
    assert "gb_test_xxxxxxxxxxxxxxxxxxxxxxx" not in repr(client)


def test_sync_strips_trailing_slash() -> None:
    client = GhostBill(API_KEY, base_url=f"{BASE_URL}/")

    assert repr(client) == "GhostBill(api_key='gb_test_...', base_url='https://your-ghostbill.example')"


def test_sync_rejects_non_positive_timeout() -> None:
    with pytest.raises(ConfigurationError):
        GhostBill(API_KEY, base_url=BASE_URL, timeout=0)

    with pytest.raises(ConfigurationError):
        GhostBill(API_KEY, base_url=BASE_URL, timeout=-1)


def test_sync_rejects_negative_max_retries() -> None:
    with pytest.raises(ConfigurationError):
        GhostBill(API_KEY, base_url=BASE_URL, max_retries=-1)


def test_async_requires_api_key() -> None:
    with pytest.raises(ConfigurationError):
        AsyncGhostBill(base_url=BASE_URL)


def test_async_requires_base_url() -> None:
    with pytest.raises(ConfigurationError):
        AsyncGhostBill(api_key=API_KEY)


def test_async_uses_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHOSTBILL_API_KEY", API_KEY)
    monkeypatch.setenv("GHOSTBILL_BASE_URL", BASE_URL)

    client = AsyncGhostBill()

    assert "gb_test_..." in repr(client)
    assert BASE_URL in repr(client)


def test_async_repr_masks_key() -> None:
    client = AsyncGhostBill("gb_test_xxxxxxxxxxxxxxxxxxxxxxx", base_url=BASE_URL)

    assert "gb_test_..." in repr(client)
    assert "gb_test_xxxxxxxxxxxxxxxxxxxxxxx" not in repr(client)


def test_async_strips_trailing_slash() -> None:
    client = AsyncGhostBill(API_KEY, base_url=f"{BASE_URL}/")

    assert repr(client) == "AsyncGhostBill(api_key='gb_test_...', base_url='https://your-ghostbill.example')"


def test_async_rejects_non_positive_timeout() -> None:
    with pytest.raises(ConfigurationError):
        AsyncGhostBill(API_KEY, base_url=BASE_URL, timeout=0)

    with pytest.raises(ConfigurationError):
        AsyncGhostBill(API_KEY, base_url=BASE_URL, timeout=-1)


def test_async_rejects_negative_max_retries() -> None:
    with pytest.raises(ConfigurationError):
        AsyncGhostBill(API_KEY, base_url=BASE_URL, max_retries=-1)


def test_classes_are_independent() -> None:
    assert not issubclass(AsyncGhostBill, GhostBill)
    assert not issubclass(GhostBill, AsyncGhostBill)
