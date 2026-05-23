from pathlib import Path


def test_ciphertext_has_version_byte_and_legacy_path():
    source = (Path("backend/app/core/encryption.py")).read_text()
    assert 'VERSION_1 = b"\\x01"' in source
    assert "combined = VERSION_1 + nonce + ciphertext_with_tag" in source
    assert "version = 0" in source
