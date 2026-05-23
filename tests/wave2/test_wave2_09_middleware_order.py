from app.main import app
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing_jitter import TimingJitterMiddleware


def test_middleware_order_rate_limiter_innermost():
    classes = [m.cls for m in app.user_middleware]
    assert classes.index(TimingJitterMiddleware) < classes.index(SecurityHeadersMiddleware)
    assert classes.index(SecurityHeadersMiddleware) < classes.index(RateLimiterMiddleware)
