"""Shared pytest fixtures for the GhostBill SDK scaffold."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_ghostbill_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GHOSTBILL_API_KEY", raising=False)
    monkeypatch.delenv("GHOSTBILL_BASE_URL", raising=False)
