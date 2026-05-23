import types

import pytest

from app.core.rate_limit import RateLimitResult
from app.middleware.rate_limiter import RateLimiterMiddleware


class Redis:
    pass


@pytest.mark.asyncio
async def test_over_limit_merchant_request_does_not_call_endpoint():
    middleware = RateLimiterMiddleware(app=None, redis=Redis())
    middleware._limiter = types.SimpleNamespace(check=lambda *_: RateLimitResult(True, 100, 99, 60))
    middleware._merchant_limiter = types.SimpleNamespace(check=lambda *_: RateLimitResult(False, 1, 0, 60, 60))

    async def ip_check(*_):
        return RateLimitResult(True, 100, 99, 60)

    async def merchant_check(*_):
        return RateLimitResult(False, 1, 0, 60, 60)

    middleware._limiter.check = ip_check
    middleware._merchant_limiter.check = merchant_check

    called = False

    async def call_next(_request):
        nonlocal called
        called = True

    request = types.SimpleNamespace(
        url=types.SimpleNamespace(path="/v1/invoices"),
        method="POST",
        headers={"authorization": "Bearer gb_live_" + "a" * 32},
        client=types.SimpleNamespace(host="203.0.113.5"),
        app=types.SimpleNamespace(state=types.SimpleNamespace(redis=Redis())),
        state=types.SimpleNamespace(),
    )
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 429
    assert called is False
