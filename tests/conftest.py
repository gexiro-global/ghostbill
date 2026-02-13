"""
GhostBill — Shared test fixtures and helpers.

Integration tests against live backend at 127.0.0.1:8013.
Direct DB access via asyncpg for payment simulation (INSERT).

Usage:
    cd /root/ghostbill && python3 -m pytest tests/ -v
"""

import hashlib
import hmac
import json
import os
import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
import pytest_asyncio

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_URL = os.getenv("GHOSTBILL_TEST_URL", "http://127.0.0.1:8013")
DB_DSN = os.getenv(
    "GHOSTBILL_TEST_DB",
    "postgresql://ghostbill:f5e1286a040ede55a15f93f02ce2b07e7ea42011748a037b7d4acc6040f1fe3a@127.0.0.1:5445/ghostbill",
)

KNOWN_LIVE_KEY = "gb_live_5d347e8b575d6d546f7f8af504461ce7"
TEST_VIEW_KEY = "a" * 64
PICONERO = 10**12
DUST_THRESHOLD_ATOMIC = 100_000_000

# ─── Module-level cache ──────────────────────────────────────────────────────

_cached_merchant: dict[str, Any] | None = None


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    """Async HTTP client — simple, no async teardown issues."""
    c = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)
    yield c
    # Don't use async close - avoids event loop closed errors
    try:
        await c.aclose()
    except RuntimeError:
        pass


# ─── DB helper: fresh connection per operation ───────────────────────────────


async def _get_conn() -> asyncpg.Connection:
    """Get a fresh DB connection on the current event loop."""
    return await asyncpg.connect(dsn=DB_DSN)


async def db_execute(query: str, *args) -> None:
    conn = await _get_conn()
    try:
        await conn.execute(query, *args)
    finally:
        await conn.close()


async def db_fetchrow(query: str, *args) -> asyncpg.Record | None:
    conn = await _get_conn()
    try:
        return await conn.fetchrow(query, *args)
    finally:
        await conn.close()


async def db_fetch(query: str, *args) -> list[asyncpg.Record]:
    conn = await _get_conn()
    try:
        return await conn.fetch(query, *args)
    finally:
        await conn.close()


# ─── Auth Headers ────────────────────────────────────────────────────────────


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


# ─── Merchant Registration ──────────────────────────────────────────────────


def generate_unique_address() -> str:
    suffix = "".join(random.choices("0123456789abcdef", k=94))
    return "4" + suffix


async def _register_merchant(client: httpx.AsyncClient, name_prefix: str = "Test") -> dict[str, Any]:
    address = generate_unique_address()
    payload = {
        "primary_address": address,
        "view_key": TEST_VIEW_KEY,
        "name": f"{name_prefix}Merchant_{uuid.uuid4().hex[:8]}",
        "email": "test@ghostbill.local",
    }
    resp = await client.post("/v1/merchants", json=payload)
    assert resp.status_code == 201, f"Registration failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return {
        "merchant_id": data["merchant_id"],
        "api_key_live": data["api_keys"]["live"],
        "api_key_test": data["api_keys"]["test"],
        "webhook_secret": data["webhook_secret"],
        "monero_address": address,
    }


@pytest_asyncio.fixture
async def test_merchant(client: httpx.AsyncClient) -> dict[str, Any]:
    """Cached test merchant — reuses across tests."""
    global _cached_merchant
    if _cached_merchant is not None:
        resp = await client.get(
            "/v1/merchants/me",
            headers=auth_headers(_cached_merchant["api_key_live"]),
        )
        if resp.status_code == 200:
            return _cached_merchant
        _cached_merchant = None

    _cached_merchant = await _register_merchant(client, "Test")
    return _cached_merchant


@pytest_asyncio.fixture
async def fresh_merchant(client: httpx.AsyncClient) -> dict[str, Any]:
    """Brand new merchant for a single test (never cached)."""
    return await _register_merchant(client, "Fresh")


# ─── Invoice Helpers ─────────────────────────────────────────────────────────


async def create_invoice(
    client: httpx.AsyncClient,
    api_key: str,
    amount_xmr: str = "0.5",
    description: str | None = "Test invoice",
    expires_in: int | None = 3600,
    metadata: dict | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"amount_xmr": amount_xmr}
    if description is not None:
        payload["description"] = description
    if expires_in is not None:
        payload["expires_in"] = expires_in
    if metadata is not None:
        payload["metadata"] = metadata

    resp = await client.post(
        "/v1/invoices", json=payload, headers=auth_headers(api_key),
    )
    assert resp.status_code == 201, f"Invoice creation failed: {resp.status_code} {resp.text}"
    return resp.json()


async def get_invoice(
    client: httpx.AsyncClient,
    api_key: str,
    invoice_id: str,
) -> dict[str, Any]:
    resp = await client.get(
        f"/v1/invoices/{invoice_id}", headers=auth_headers(api_key),
    )
    assert resp.status_code == 200, f"Get invoice failed: {resp.status_code} {resp.text}"
    return resp.json()


# ─── Payment Simulation (Direct DB INSERT) ───────────────────────────────────


def generate_fake_tx_hash() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


async def insert_simulated_payment(
    invoice_id: str,
    amount_atomic: int,
    tx_hash: str | None = None,
    status: str = "detected",
    confirmations: int = 0,
    block_height: int | None = None,
) -> dict[str, Any]:
    """Insert a simulated payment directly into the DB."""
    if tx_hash is None:
        tx_hash = generate_fake_tx_hash()

    payment_id = str(uuid.uuid4())
    amount_xmr = str(Decimal(str(amount_atomic)) / Decimal(str(PICONERO)))
    now = datetime.now(timezone.utc)
    confirmed_at = now if status == "confirmed" else None

    await db_execute(
        """
        INSERT INTO payments (
            id, invoice_id, tx_hash, amount_atomic, amount_xmr,
            status, confirmations, block_height,
            detected_at, confirmed_at, created_at
        ) VALUES (
            $1::uuid, $2::uuid, $3, $4, $5,
            $6::payment_status, $7, $8,
            $9, $10, $9
        )
        """,
        uuid.UUID(payment_id),
        uuid.UUID(invoice_id),
        tx_hash,
        amount_atomic,
        Decimal(amount_xmr),
        status,
        confirmations,
        block_height,
        now,
        confirmed_at,
    )

    return {
        "id": payment_id,
        "invoice_id": invoice_id,
        "tx_hash": tx_hash,
        "amount_atomic": amount_atomic,
        "status": status,
        "confirmations": confirmations,
    }


async def update_invoice_status_db(invoice_id: str, new_status: str, paid_at: datetime | None = None) -> None:
    if paid_at is not None:
        await db_execute(
            "UPDATE invoices SET status = $1::invoice_status, paid_at = $2, updated_at = NOW() WHERE id = $3::uuid",
            new_status, paid_at, uuid.UUID(invoice_id),
        )
    else:
        await db_execute(
            "UPDATE invoices SET status = $1::invoice_status, updated_at = NOW() WHERE id = $2::uuid",
            new_status, uuid.UUID(invoice_id),
        )


async def expire_invoice_db(invoice_id: str) -> None:
    await db_execute(
        "UPDATE invoices SET status = 'expired'::invoice_status, expires_at = NOW() - INTERVAL '1 hour', updated_at = NOW() WHERE id = $1::uuid",
        uuid.UUID(invoice_id),
    )


async def get_invoice_status_db(invoice_id: str) -> str:
    row = await db_fetchrow("SELECT status FROM invoices WHERE id = $1::uuid", uuid.UUID(invoice_id))
    assert row is not None, f"Invoice {invoice_id} not found in DB"
    return row["status"]


async def count_payments_for_invoice(invoice_id: str, status: str | None = None) -> int:
    if status is not None:
        row = await db_fetchrow(
            "SELECT COUNT(*) as cnt FROM payments WHERE invoice_id = $1::uuid AND status = $2::payment_status",
            uuid.UUID(invoice_id), status,
        )
    else:
        row = await db_fetchrow(
            "SELECT COUNT(*) as cnt FROM payments WHERE invoice_id = $1::uuid",
            uuid.UUID(invoice_id),
        )
    return row["cnt"]


async def sum_payments_for_invoice(invoice_id: str) -> int:
    row = await db_fetchrow(
        "SELECT COALESCE(SUM(amount_atomic), 0) as total FROM payments WHERE invoice_id = $1::uuid AND status IN ('detected', 'confirmed')",
        uuid.UUID(invoice_id),
    )
    return int(row["total"])


async def update_payment_status_db(payment_id: str, new_status: str) -> None:
    await db_execute(
        "UPDATE payments SET status = $1::payment_status WHERE id = $2::uuid",
        new_status, uuid.UUID(payment_id),
    )


# ─── Webhook Helpers ─────────────────────────────────────────────────────────


def verify_webhook_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(key=secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def get_webhook_deliveries_db(invoice_id: str) -> list[dict[str, Any]]:
    rows = await db_fetch(
        "SELECT id, event_type, status, payload, attempts, url, response_code, created_at FROM webhook_deliveries WHERE invoice_id = $1::uuid ORDER BY created_at ASC",
        uuid.UUID(invoice_id),
    )
    return [dict(row) for row in rows]


# ─── Cleanup ─────────────────────────────────────────────────────────────────


async def cleanup_merchant_data(merchant_id: str) -> None:
    mid = uuid.UUID(merchant_id)
    conn = await _get_conn()
    try:
        invoice_rows = await conn.fetch("SELECT id FROM invoices WHERE merchant_id = $1::uuid", mid)
        invoice_ids = [row["id"] for row in invoice_rows]

        if invoice_ids:
            await conn.execute("DELETE FROM payments WHERE invoice_id = ANY($1::uuid[])", invoice_ids)
            await conn.execute("DELETE FROM invoice_addresses WHERE invoice_id = ANY($1::uuid[])", invoice_ids)

        await conn.execute("DELETE FROM webhook_deliveries WHERE merchant_id = $1::uuid", mid)
        await conn.execute("DELETE FROM audit_log WHERE merchant_id = $1::uuid", mid)
        await conn.execute("DELETE FROM invoices WHERE merchant_id = $1::uuid", mid)
        await conn.execute("DELETE FROM api_keys WHERE merchant_id = $1::uuid", mid)
        await conn.execute("DELETE FROM wallet_shards WHERE merchant_id = $1::uuid", mid)
        await conn.execute("DELETE FROM merchants WHERE id = $1::uuid", mid)
    finally:
        await conn.close()


# ─── Health check (sync, at collection time) ────────────────────────────────


def pytest_configure(config):
    import urllib.request
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/health", timeout=5)
        data = json.loads(req.read())
        if data.get("status") != "healthy":
            raise Exception(f"Backend unhealthy: {data}")
    except Exception as exc:
        raise SystemExit(f"Backend not healthy at {BASE_URL}: {exc}")
