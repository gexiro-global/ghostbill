import pytest

from app.core.rate_limit import MerchantRateLimiter


class Redis:
    def pipeline(self, transaction=True):
        raise RuntimeError("redis unavailable")


@pytest.mark.asyncio
async def test_redis_fail_closed_denies():
    result = await MerchantRateLimiter(Redis(), fail_open=False).check("merchant", "write")
    assert result.allowed is False
    assert result.retry_after is not None


@pytest.mark.asyncio
async def test_redis_fail_open_allows():
    result = await MerchantRateLimiter(Redis(), fail_open=True).check("merchant", "read")
    assert result.allowed is True
