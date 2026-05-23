from app.middleware.rate_limiter import PUBLIC_API_PATTERN


def test_sse_path_uses_public_api_pattern():
    assert PUBLIC_API_PATTERN.match("/v1/invoices/123e4567-e89b-12d3-a456-426614174000/events")
