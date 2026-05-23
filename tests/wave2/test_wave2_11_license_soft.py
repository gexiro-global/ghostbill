import logging

import pytest

from app.services.license_service import check_tier_limit


class Scalar:
    def scalar_one(self):
        return 1


class DB:
    async def execute(self, _stmt):
        return Scalar()


@pytest.mark.asyncio
async def test_license_limit_warning_but_allowed(caplog):
    caplog.set_level(logging.WARNING)
    result = await check_tier_limit(DB(), "merchant-id", "analytics")
    assert result.allowed is True
    assert result.over_limit is True
    assert "LICENSE_TIER_LIMIT_SOFT" in caplog.text
