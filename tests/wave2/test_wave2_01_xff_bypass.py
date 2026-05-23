import types

from app.middleware.rate_limiter import EXEMPT_IPS, RateLimiterMiddleware


def _request(peer: str, xff: str | None = None):
    headers = {"x-forwarded-for": xff} if xff else {}
    return types.SimpleNamespace(headers=headers, client=types.SimpleNamespace(host=peer))


def test_spoofed_xff_from_untrusted_peer_is_not_exempt():
    middleware = RateLimiterMiddleware(app=None)
    client_ip = middleware._get_client_ip(_request("203.0.113.9", "127.0.0.1"))
    assert client_ip == "203.0.113.9"
    assert client_ip not in EXEMPT_IPS


def test_xff_from_trusted_proxy_is_used():
    middleware = RateLimiterMiddleware(app=None)
    assert middleware._get_client_ip(_request("172.17.0.1", "198.51.100.7")) == "198.51.100.7"
