from pathlib import Path


def test_base64_decode_is_strict():
    source = (Path("backend/app/core/encryption.py")).read_text()
    assert "base64.b64decode(encrypted_b64, validate=True)" in source
    assert "binascii.Error" in source
