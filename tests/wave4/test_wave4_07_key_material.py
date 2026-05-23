from pathlib import Path


def test_key_material_is_256_bit_hex():
    source = (Path("backend/app/core/security.py")).read_text()
    assert "API_KEY_HEX_LENGTH = 64" in source
    assert "WEBHOOK_SECRET_LENGTH = 64" in source
    assert "secrets.token_hex(API_KEY_HEX_LENGTH // 2)" in source
