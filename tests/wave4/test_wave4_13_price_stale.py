from pathlib import Path


def test_price_ttl_matches_stale_threshold():
    source = (Path("backend/app/services/price_feed.py")).read_text()
    assert "CACHE_TTL_SECONDS = STALE_THRESHOLD_SECONDS" in source
