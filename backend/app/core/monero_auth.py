"""
Monero signature authentication service.

Provides privacy-first login for dashboard:
    1. Merchant requests nonce (bound to their Monero address)
    2. Merchant signs nonce locally with monero-wallet-cli
    3. Server verifies signature via wallet-rpc
    4. Server issues session token (gbs_<hex64>)

Nonce: single-use, 5 min TTL, stored in Redis.
Session: 24h TTL, stored in Redis only (not DB).

This is OPTIONAL — Bearer API keys (gb_live_/gb_test_) remain primary auth.
Monero signature is for maximum-privacy merchants.
"""

import logging
import os
import re
import time
from typing import Any

from redis.asyncio import Redis

from app.services.monero_rpc import get_monero_rpc

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

NONCE_TTL_SECONDS: int = 300  # 5 minutes
NONCE_PREFIX: str = "ghostbill_nonce:"
SESSION_PREFIX: str = "ghostbill_session:"
SESSION_TTL_SECONDS: int = 86400  # 24 hours
SESSION_TOKEN_PREFIX: str = "gbs_"

# Monero primary address: 95 chars, starts with 4
MONERO_ADDRESS_REGEX = re.compile(r"^4[1-9A-HJ-NP-Za-km-z]{94}$")

# Monero signature format: starts with SigV
MONERO_SIGNATURE_REGEX = re.compile(r"^SigV\d+[A-Za-z0-9+/=]+$")


# ─── Address Validation ─────────────────────────────────────────────────────

def validate_monero_address(address: str) -> bool:
    """Validate Monero primary address format.

    Rules:
        - 95 characters
        - Starts with '4'
        - Base58 character set
    """
    if not address or not isinstance(address, str):
        return False
    return bool(MONERO_ADDRESS_REGEX.match(address))


def validate_signature_format(signature: str) -> bool:
    """Basic format check for Monero signature string."""
    if not signature or not isinstance(signature, str):
        return False
    return bool(MONERO_SIGNATURE_REGEX.match(signature))


# ─── Nonce Management ───────────────────────────────────────────────────────

async def generate_nonce(redis: Redis, address: str) -> str:
    """Generate a single-use nonce bound to a Monero address.

    Format: ghostbill_<random32hex>_<unix_timestamp>

    Stored in Redis:
        key: ghostbill_nonce:<nonce_value>
        value: address
        TTL: 300 seconds (5 minutes)

    Args:
        redis: Redis connection.
        address: Monero primary address.

    Returns:
        Nonce string.
    """
    random_hex = os.urandom(16).hex()  # 32 hex chars
    timestamp = int(time.time())
    nonce = f"ghostbill_{random_hex}_{timestamp}"

    redis_key = f"{NONCE_PREFIX}{nonce}"
    await redis.setex(redis_key, NONCE_TTL_SECONDS, address)

    logger.info("Nonce generated for address %s...%s", address[:8], address[-6:])
    return nonce


async def validate_nonce(redis: Redis, nonce: str, address: str) -> tuple[bool, str]:
    """Validate and consume a nonce.

    Checks:
        1. Nonce exists in Redis (not expired)
        2. Nonce is bound to the given address
        3. Delete after validation (single-use)

    Args:
        redis: Redis connection.
        nonce: Nonce string to validate.
        address: Monero address that requested this nonce.

    Returns:
        (valid, error_message)
    """
    redis_key = f"{NONCE_PREFIX}{nonce}"

    # Atomic get-and-delete
    stored_address = await redis.getdel(redis_key)

    if stored_address is None:
        return False, "Nonce expired or already used"

    stored_address = stored_address.decode("utf-8") if isinstance(stored_address, bytes) else stored_address

    if stored_address != address:
        logger.warning(
            "Nonce address mismatch: expected %s...%s, got %s...%s",
            stored_address[:8], stored_address[-6:],
            address[:8], address[-6:],
        )
        return False, "Nonce not bound to this address"

    return True, ""


# ─── Signature Verification ─────────────────────────────────────────────────

async def verify_monero_signature(
    address: str, data: str, signature: str
) -> bool:
    """Verify Monero signature via wallet-rpc.

    Calls the 'verify' RPC method on monero-wallet-rpc.

    Args:
        address: Monero primary address of the signer.
        data: The data that was signed (nonce string).
        signature: The signature produced by monero-wallet-cli.

    Returns:
        True if signature is valid for the given address and data.
    """
    try:
        rpc = get_monero_rpc()
        result = await rpc._call("verify", {
            "data": data,
            "address": address,
            "signature": signature,
        })
        is_good = result.get("good", False)

        if is_good:
            logger.info(
                "Signature verified for address %s...%s",
                address[:8], address[-6:],
            )
        else:
            logger.warning(
                "Invalid signature for address %s...%s",
                address[:8], address[-6:],
            )

        return is_good

    except Exception as exc:
        logger.error("Signature verification RPC error: %s", exc)
        return False


# ─── Session Management ─────────────────────────────────────────────────────

async def create_session(redis: Redis, merchant_id: str) -> str:
    """Create a session token after successful signature verification.

    Token format: gbs_<random64hex>
    Stored in Redis:
        key: ghostbill_session:gbs_<token>
        value: merchant_id
        TTL: 86400 seconds (24 hours)

    Args:
        redis: Redis connection.
        merchant_id: UUID string of the authenticated merchant.

    Returns:
        Session token string (gbs_...).
    """
    random_hex = os.urandom(32).hex()  # 64 hex chars
    token = f"{SESSION_TOKEN_PREFIX}{random_hex}"

    redis_key = f"{SESSION_PREFIX}{token}"
    await redis.setex(redis_key, SESSION_TTL_SECONDS, merchant_id)

    logger.info("Session created for merchant %s", merchant_id)
    return token


async def validate_session(redis: Redis, token: str) -> str | None:
    """Validate a session token and return merchant_id.

    Args:
        redis: Redis connection.
        token: Session token (gbs_...).

    Returns:
        merchant_id string if valid, None if expired/invalid.
    """
    if not token.startswith(SESSION_TOKEN_PREFIX):
        return None

    redis_key = f"{SESSION_PREFIX}{token}"
    merchant_id = await redis.get(redis_key)

    if merchant_id is None:
        return None

    return merchant_id.decode("utf-8") if isinstance(merchant_id, bytes) else merchant_id


async def revoke_session(redis: Redis, token: str) -> bool:
    """Revoke (delete) a session token.

    Args:
        redis: Redis connection.
        token: Session token to revoke.

    Returns:
        True if session existed and was deleted.
    """
    redis_key = f"{SESSION_PREFIX}{token}"
    deleted = await redis.delete(redis_key)
    return deleted > 0
