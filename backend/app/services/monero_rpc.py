"""
Async wrapper for monero-wallet-rpc JSON-RPC.

CRITICAL: All amounts from RPC are in ATOMIC UNITS (piconero).
1 XMR = 1_000_000_000_000 piconero (10^12)

Connection: httpx async -> http://host:port/json_rpc
Auth: Digest auth (user/pass from .env)
Error handling: Retry 3x with exponential backoff
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PICONERO: int = 10**12
DUST_THRESHOLD_ATOMIC: int = 100_000_000  # 0.0001 XMR

MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 1.0  # seconds


def atomic_to_xmr(atomic: int) -> Decimal:
    """Convert piconero (atomic units) to XMR as Decimal."""
    return Decimal(str(atomic)) / Decimal(str(PICONERO))


def xmr_to_atomic(xmr: Decimal) -> int:
    """Convert XMR (Decimal) to piconero (atomic units)."""
    return int(xmr * Decimal(str(PICONERO)))


class MoneroRPCError(Exception):
    """Base exception for wallet-rpc errors."""

    def __init__(self, message: str, code: int | None = None, data: Any = None):
        self.message = message
        self.code = code
        self.data = data
        super().__init__(message)


class MoneroRPCConnectionError(MoneroRPCError):
    """Connection to wallet-rpc failed after retries."""

    pass


class MoneroRPC:
    """Async wrapper for monero-wallet-rpc JSON-RPC.

    Usage:
        rpc = MoneroRPC()
        height = await rpc.get_height()
        await rpc.close()
    """

    def __init__(self) -> None:
        self._url = f"http://{settings.wallet_rpc_host}:{settings.wallet_rpc_port}/json_rpc"
        self._auth = httpx.DigestAuth(
            username=settings.wallet_rpc_user,
            password=settings.wallet_rpc_pass,
        )
        self._client: httpx.AsyncClient | None = None
        self._request_id: int = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=self._auth,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _call(self, method: str, params: dict | None = None) -> Any:
        """Execute a JSON-RPC call with retry logic.

        Returns the 'result' field from the JSON-RPC response.
        Raises MoneroRPCError on RPC-level errors.
        Raises MoneroRPCConnectionError after exhausting retries.
        """
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._request_id),
            "method": method,
        }
        if params:
            payload["params"] = params

        last_exception: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                client = await self._get_client()
                response = await client.post(self._url, json=payload)
                response.raise_for_status()
                data = response.json()

                # Check for JSON-RPC error
                if "error" in data:
                    err = data["error"]
                    raise MoneroRPCError(
                        message=err.get("message", "Unknown RPC error"),
                        code=err.get("code"),
                        data=err.get("data"),
                    )

                return data.get("result", {})

            except MoneroRPCError:
                # RPC-level errors: don't retry, propagate immediately
                raise

            except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
                last_exception = exc
                wait = RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "wallet-rpc %s attempt %d/%d failed: %s. Retrying in %.1fs",
                    method,
                    attempt + 1,
                    MAX_RETRIES,
                    str(exc),
                    wait,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                    # Force new client on connection errors
                    await self.close()

        raise MoneroRPCConnectionError(f"wallet-rpc {method} failed after {MAX_RETRIES} retries: {last_exception}")

    async def get_height(self) -> int:
        """Return current blockchain height seen by wallet-rpc."""
        result = await self._call("get_height")
        return int(result["height"])

    async def get_version(self) -> str:
        """Return wallet-rpc version string."""
        result = await self._call("get_version")
        return str(result.get("version", "unknown"))

    async def create_address(self, account_index: int = 0, label: str = "") -> dict:
        """Create a new subaddress.

        Args:
            account_index: Always 0 (single account, view-only wallet).
            label: Label for the subaddress (e.g. "inv_<uuid_short>").

        Returns:
            {"address": "8...", "address_index": 42}
        """
        result = await self._call(
            "create_address",
            {"account_index": account_index, "label": label},
        )
        return {
            "address": result["address"],
            "address_index": result["address_index"],
        }

    async def get_transfers(
        self,
        account_index: int = 0,
        min_height: int = 0,
        max_height: int = 0,
        pool: bool = True,
        in_: bool = True,
        filter_by_height: bool = True,
    ) -> list[dict]:
        """Get incoming transfers including mempool.

        CRITICAL: pool=True is required to see unconfirmed TX in mempool.

        Each transfer contains:
            - amount: int (ATOMIC UNITS / piconero)
            - subaddr_index: {"major": 0, "minor": 42}
            - confirmations: int
            - height: int (0 if mempool)
            - txid: str
            - type: "in" | "pool"

        Returns:
            Combined list of confirmed ("in") and mempool ("pool") transfers.
        """
        params: dict[str, Any] = {
            "account_index": account_index,
            "in": in_,
            "pool": pool,
            "filter_by_height": filter_by_height,
        }
        if filter_by_height and min_height > 0:
            params["min_height"] = min_height
        if filter_by_height and max_height > 0:
            params["max_height"] = max_height

        result = await self._call("get_transfers", params)

        # Merge confirmed + mempool transfers
        transfers: list[dict] = []
        if in_ and "in" in result:
            transfers.extend(result["in"])
        if pool and "pool" in result:
            transfers.extend(result["pool"])

        return transfers

    async def get_transfer_by_txid(self, txid: str) -> dict | None:
        """Get a single transfer by transaction ID.

        Used for confirmation tracking and dispute resolution.

        Returns:
            Transfer dict or None if not found.
        """
        try:
            result = await self._call(
                "get_transfer_by_txid",
                {"txid": txid},
            )
            transfer = result.get("transfer")
            if transfer is None:
                return None
            return transfer
        except MoneroRPCError as exc:
            # wallet-rpc returns error if txid not found
            if exc.code == -8 or "not found" in exc.message.lower():
                return None
            raise

    async def get_balance(self, account_index: int = 0) -> dict:
        """Get wallet balance.

        Returns:
            {
                "balance": int (atomic),
                "unlocked_balance": int (atomic)
            }
        """
        result = await self._call(
            "get_balance",
            {"account_index": account_index},
        )
        return {
            "balance": int(result["balance"]),
            "unlocked_balance": int(result["unlocked_balance"]),
        }

    async def check_tx_key(self, txid: str, tx_key: str, address: str) -> dict:
        """Verify a payment using tx secret key.

        Used for dispute resolution when merchant claims non-payment.

        Returns:
            {"confirmed": bool, "received": int (atomic)}
        """
        result = await self._call(
            "check_tx_key",
            {
                "txid": txid,
                "tx_key": tx_key,
                "address": address,
            },
        )
        return {
            "confirmed": result.get("good", False),
            "received": int(result.get("received", 0)),
        }


_rpc_instance: MoneroRPC | None = None


def get_monero_rpc() -> MoneroRPC:
    """Get or create the global MoneroRPC instance."""
    global _rpc_instance
    if _rpc_instance is None:
        _rpc_instance = MoneroRPC()
    return _rpc_instance


async def close_monero_rpc() -> None:
    """Close the global MoneroRPC instance."""
    global _rpc_instance
    if _rpc_instance is not None:
        await _rpc_instance.close()
        _rpc_instance = None
