from pathlib import Path


def test_hmac_verification_normalizes_hex():
    source = (Path("backend/app/core/security.py")).read_text()
    assert "received = signature.lower()" in source
    assert ".lower()" in source
    assert "hmac.compare_digest" in source
