"""
Security utilities for GhostBill.

- API key generation: gb_live_<hex> / gb_test_<hex>
- Key hashing: bcrypt (cost >= 12)
- Key verification: bcrypt verify (constant-time by design)
- HMAC-SHA256: webhook signatures (X-GhostBill-Signature)
- Webhook secret generation
"""

import hashlib
import hmac
import logging
import secrets

import bcrypt

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

API_KEY_PREFIX_LIVE = "gb_live_"
API_KEY_PREFIX_TEST = "gb_test_"
API_KEY_HEX_LENGTH = 32  # 32 hex chars = 16 bytes entropy
BCRYPT_ROUNDS = 12
WEBHOOK_SECRET_LENGTH = 32  # 32 hex chars


# ─── API Key Generation ─────────────────────────────────────────────────────

def generate_api_key(environment: str = "live") -> str:
    """Generate a new API key.

    Format: gb_live_<32hex> or gb_test_<32hex>
    NEVER use ghk_ prefix.

    Args:
        environment: "live" or "test"

    Returns:
        Plain-text API key (shown to merchant ONCE, never stored).
    """
    if environment not in ("live", "test"):
        raise ValueError(f"Invalid environment: {environment}. Must be 'live' or 'test'.")

    prefix = API_KEY_PREFIX_LIVE if environment == "live" else API_KEY_PREFIX_TEST
    random_hex = secrets.token_hex(API_KEY_HEX_LENGTH // 2)  # 16 bytes = 32 hex chars
    return f"{prefix}{random_hex}"


# ─── Bcrypt Hash / Verify ───────────────────────────────────────────────────

def hash_api_key(plain_key: str) -> str:
    """Hash an API key with bcrypt (cost >= 12).

    Args:
        plain_key: The full API key (e.g. gb_live_abc123...).

    Returns:
        bcrypt hash string (stored in api_keys.key_hash).
    """
    key_bytes = plain_key.encode("utf-8")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(key_bytes, salt)
    return hashed.decode("utf-8")


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its bcrypt hash.

    bcrypt.checkpw is constant-time by design (no timing side-channel).

    Args:
        plain_key: The API key from Authorization header.
        hashed_key: The bcrypt hash from DB (api_keys.key_hash).

    Returns:
        True if match, False otherwise.
    """
    try:
        return bcrypt.checkpw(
            plain_key.encode("utf-8"),
            hashed_key.encode("utf-8"),
        )
    except (ValueError, TypeError) as exc:
        logger.warning("bcrypt verify failed: %s", exc)
        return False


# ─── HMAC-SHA256 (Webhooks) ─────────────────────────────────────────────────

def hmac_sign(payload: bytes, secret: str) -> str:
    """Create HMAC-SHA256 signature for webhook payload.

    Used in X-GhostBill-Signature header.

    Args:
        payload: Raw request body bytes.
        secret: Merchant's webhook_secret.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()


def hmac_verify(payload: bytes, secret: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature (constant-time compare).

    Args:
        payload: Raw request body bytes.
        secret: Merchant's webhook_secret.
        signature: Signature from X-GhostBill-Signature header.

    Returns:
        True if signature is valid.
    """
    expected = hmac_sign(payload, secret)
    return hmac.compare_digest(expected, signature)


# ─── Webhook Secret ─────────────────────────────────────────────────────────

def generate_webhook_secret() -> str:
    """Generate a random webhook signing secret.

    Returns:
        Hex string (32 chars = 16 bytes entropy).
    """
    return secrets.token_hex(WEBHOOK_SECRET_LENGTH // 2)


# ─── Bearer Token Parsing ───────────────────────────────────────────────────

def parse_bearer_token(authorization: str | None) -> str | None:
    """Extract token from 'Authorization: Bearer <token>' header.

    Args:
        authorization: Full Authorization header value.

    Returns:
        The token string, or None if header is missing/malformed.
    """
    if not authorization:
        return None

    parts = authorization.split(" ", maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()
    if not token:
        return None

    return token


def get_key_environment(api_key: str) -> str | None:
    """Determine environment from API key prefix.

    Args:
        api_key: Plain-text API key.

    Returns:
        "live", "test", or None if prefix is invalid.
    """
    if api_key.startswith(API_KEY_PREFIX_LIVE):
        return "live"
    elif api_key.startswith(API_KEY_PREFIX_TEST):
        return "test"
    return None
