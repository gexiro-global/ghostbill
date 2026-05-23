"""
AES-256-GCM encryption for sensitive data (merchant view keys).

Master key loaded from MASTER_ENCRYPTION_KEY env var (64 hex chars = 32 bytes).
Each encryption generates a unique 12-byte nonce (os.urandom).
Output format: base64(nonce_12bytes + ciphertext + tag_16bytes).

CRITICAL:
- Master key NEVER in DB. Only in .env (future: HashiCorp Vault).
- If master key is lost, all encrypted data is unrecoverable.
- Nonce MUST be unique per encryption (os.urandom guarantees this).
"""

import base64
import binascii
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

NONCE_SIZE = 12  # 96-bit nonce for AES-GCM
VERSION_1 = b"\x01"


class EncryptionError(Exception):
    """Raised when encryption fails."""

    pass


class DecryptionError(Exception):
    """Raised when decryption fails (wrong key, corrupted data, tampered)."""

    pass


class ViewKeyEncryption:
    """AES-256-GCM encryption for merchant view keys.

    Master key source:
    - Current: .env (MASTER_ENCRYPTION_KEY=<64 hex chars>)
    - Production: HashiCorp Vault (post-MVP)
    """

    def __init__(self, master_key_hex: str):
        if not master_key_hex:
            raise EncryptionError("MASTER_ENCRYPTION_KEY is not set. Generate with: openssl rand -hex 32")

        try:
            key_bytes = bytes.fromhex(master_key_hex)
        except ValueError as e:
            raise EncryptionError(f"MASTER_ENCRYPTION_KEY is not valid hex: {e}")

        if len(key_bytes) != 32:
            raise EncryptionError(f"MASTER_ENCRYPTION_KEY must be 32 bytes (64 hex chars), got {len(key_bytes)} bytes")

        # Process memory is GhostBill's trusted boundary in self-hosted deployments.
        # TODO: Consider key-from-HSM or per-request derivation for hardened deployments.
        self._aesgcm = AESGCM(key_bytes)
        logger.info("ViewKeyEncryption initialized successfully")

    @staticmethod
    def _aad(merchant_id: str | None = None, aad: bytes | str | None = None) -> bytes | None:
        if aad is not None:
            return aad.encode("utf-8") if isinstance(aad, str) else aad
        if merchant_id is not None:
            return f"ghostbill:viewkey:{merchant_id}".encode("utf-8")
        return None

    def encrypt(self, plaintext: str, merchant_id: str | None = None, aad: bytes | str | None = None) -> str:
        """Encrypt plaintext string -> base64 encoded string.

        Output format: base64(nonce[12] + ciphertext + tag[16])
        Nonce is generated fresh for each call (os.urandom).

        Args:
            plaintext: The view key to encrypt.

        Returns:
            Base64-encoded string containing nonce + ciphertext + tag.

        Raises:
            EncryptionError: If encryption fails.
        """
        if not plaintext:
            raise EncryptionError("Cannot encrypt empty plaintext")

        try:
            nonce = os.urandom(NONCE_SIZE)
            ciphertext_with_tag = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), self._aad(merchant_id, aad))
            # version (1) + nonce (12) + ciphertext + tag (16) = combined blob
            combined = VERSION_1 + nonce + ciphertext_with_tag
            return base64.b64encode(combined).decode("ascii")
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, encrypted_b64: str, merchant_id: str | None = None, aad: bytes | str | None = None) -> str:
        """Decrypt base64 encoded string -> plaintext string.

        Input format: base64(nonce[12] + ciphertext + tag[16])

        Args:
            encrypted_b64: Base64-encoded encrypted data.

        Returns:
            Decrypted plaintext string.

        Raises:
            DecryptionError: If decryption fails (wrong key, tampered, corrupted).
        """
        if not encrypted_b64:
            raise DecryptionError("Cannot decrypt empty input")

        try:
            combined = base64.b64decode(encrypted_b64, validate=True)
        except binascii.Error as e:
            raise DecryptionError(f"Invalid base64 input: {e}") from e

        if combined.startswith(VERSION_1):
            version = 1
            body = combined[1:]
        else:
            version = 0
            body = combined

        if len(body) < NONCE_SIZE + 16:
            raise DecryptionError(f"Encrypted data too short: {len(body)} bytes (minimum {NONCE_SIZE + 16})")

        nonce = body[:NONCE_SIZE]
        ciphertext_with_tag = body[NONCE_SIZE:]

        try:
            decrypt_aad = self._aad(merchant_id, aad) if version == 1 else None
            try:
                plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext_with_tag, decrypt_aad)
            except InvalidTag:
                if version == 1 and decrypt_aad is not None:
                    plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext_with_tag, None)
                else:
                    raise
            return plaintext_bytes.decode("utf-8")
        except InvalidTag:
            raise DecryptionError("Decryption failed: invalid tag. Wrong master key or data has been tampered with.")
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}") from e

    def re_encrypt(self, encrypted_b64: str, merchant_id: str | None = None, aad: bytes | str | None = None) -> str:
        """Decrypt and re-encrypt with a new nonce.

        Useful for key rotation preparation (same master key, new nonce).

        Args:
            encrypted_b64: Existing encrypted data.

        Returns:
            Newly encrypted data with fresh nonce.
        """
        plaintext = self.decrypt(encrypted_b64, merchant_id=merchant_id, aad=aad)
        return self.encrypt(plaintext, merchant_id=merchant_id, aad=aad)


# Singleton instance — initialized on first import
_encryption_instance: ViewKeyEncryption | None = None


def get_encryption() -> ViewKeyEncryption:
    """Get or create the singleton encryption instance.

    Loads master key from settings on first call.
    Raises EncryptionError if key is missing or invalid.
    """
    global _encryption_instance
    if _encryption_instance is None:
        from app.config import settings

        _encryption_instance = ViewKeyEncryption(settings.master_encryption_key)
    return _encryption_instance


def encrypt_view_key(view_key: str, merchant_id: str | None = None) -> str:
    """Convenience: encrypt a view key."""
    return get_encryption().encrypt(view_key, merchant_id=merchant_id)


def decrypt_view_key(encrypted: str, merchant_id: str | None = None) -> str:
    """Convenience: decrypt a view key."""
    return get_encryption().decrypt(encrypted, merchant_id=merchant_id)
