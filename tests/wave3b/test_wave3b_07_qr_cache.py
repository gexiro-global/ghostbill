from pathlib import Path

SOURCE = Path("backend/app/api/routes/public_invoice.py")


def test_public_invoice_qr_uses_redis_cache_with_address_guard():
    source = SOURCE.read_text()
    assert 'cache_key = f"qr:{invoice.id}"' in source
    assert 'cached.get("address") == address' in source
    assert "await redis.set(" in source
    assert "ex=_qr_cache_ttl(invoice.expires_at)" in source
    assert "_generate_qr_svg(monero_uri)" in source
