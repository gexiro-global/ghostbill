from pathlib import Path


def test_encryption_uses_merchant_aad():
    source = (Path("backend/app/core/encryption.py")).read_text()
    assert "ghostbill:viewkey:{merchant_id}" in source
    assert 'self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), self._aad' in source
    assert "self._aesgcm.decrypt(nonce, ciphertext_with_tag, decrypt_aad)" in source
