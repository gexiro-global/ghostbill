"""GhostBill — Coverage gap tests.

Covers previously untested areas:
    - Webhook list / get / retry  (merchant-facing)
    - DLQ list / retry  (merchant-facing)
    - Admin endpoints  (operator-facing)
    - Auth signature error paths
    - Public invoice endpoint

Requires backend running at 127.0.0.1:8013.
"""

import os
import random
import uuid
from datetime import datetime, timezone

import pytest

from tests.conftest import (
    auth_headers,
    create_invoice,
    db_execute,
)

BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def generate_base58_address() -> str:
    return "4" + "".join(random.choices(BASE58_CHARS, k=94))


async def _register_base58_merchant(client) -> dict:
    addr = generate_base58_address()
    payload = {"primary_address": addr, "view_key": "a" * 64, "name": f"AuthTest_{uuid.uuid4().hex[:8]}"}
    resp = await client.post("/v1/merchants", json=payload)
    assert resp.status_code == 201, f"Registration failed: {resp.text}"
    data = resp.json()
    return {"merchant_id": data["merchant_id"], "api_key_live": data["api_keys"]["live"], "monero_address": addr}


# ── Admin key (matches ADMIN_MERCHANT_ID in .env) ────────────────────────────

ADMIN_KEY = os.getenv("GHOSTBILL_ADMIN_KEY", "")
ADMIN_MERCHANT_ID = os.getenv("GHOSTBILL_ADMIN_MERCHANT_ID", "")


# ── DB helpers for test data ─────────────────────────────────────────────────


async def insert_webhook_delivery(
    merchant_id: str,
    event_type: str = "invoice.paid",
    status: str = "delivered",
    url: str = "http://localhost:9999/webhook",
    attempts: int = 1,
    response_code: int | None = 200,
    invoice_id: str | None = None,
) -> str:
    """Insert a test webhook delivery, return its ID."""
    delivery_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db_execute(
        """
        INSERT INTO webhook_deliveries (
            id, merchant_id, invoice_id, event_type, payload, url,
            status, attempts, max_attempts, last_attempt_at,
            response_code, created_at
        ) VALUES (
            $1::uuid, $2::uuid, $3, $4, $5::jsonb, $6,
            $7::webhook_status, $8, 7, $9,
            $10, $9
        )
        """,
        uuid.UUID(delivery_id),
        uuid.UUID(merchant_id),
        uuid.UUID(invoice_id) if invoice_id else None,
        event_type,
        '{"event": "' + event_type + '", "test": true}',
        url,
        status,
        attempts,
        now,
        response_code,
    )
    return delivery_id


async def insert_dlq_entry(
    merchant_id: str,
    delivery_id: str,
    event_type: str = "invoice.paid",
    resolved: bool = False,
) -> str:
    """Insert a test DLQ entry, return its ID."""
    dlq_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db_execute(
        """
        INSERT INTO webhook_dead_letters (
            id, delivery_id, merchant_id, event_type, payload,
            original_created_at, dead_lettered_at, retry_count,
            last_error, resolved, created_at
        ) VALUES (
            $1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb,
            $6, $6, 0,
            'Test error: connection refused', $7, $6
        )
        """,
        uuid.UUID(dlq_id),
        uuid.UUID(delivery_id),
        uuid.UUID(merchant_id),
        event_type,
        '{"event": "' + event_type + '", "test": true}',
        now,
        resolved,
    )
    return dlq_id


async def cleanup_test_webhook_data(merchant_id: str) -> None:
    """Remove test webhook/DLQ data for a merchant."""
    mid = uuid.UUID(merchant_id)
    await db_execute("DELETE FROM webhook_dead_letters WHERE merchant_id = $1::uuid", mid)
    await db_execute("DELETE FROM webhook_deliveries WHERE merchant_id = $1::uuid", mid)


# ═════════════════════════════════════════════════════════════════════════════
#  WEBHOOK ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════


class TestWebhookList:
    """GET /v1/webhooks — list deliveries."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/webhooks", headers=auth_headers(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["has_more"] is False
        print("\u2713 Webhook list empty")

    @pytest.mark.asyncio
    async def test_list_with_deliveries(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            await insert_webhook_delivery(mid, "invoice.created", "delivered")
            await insert_webhook_delivery(mid, "invoice.paid", "failed", attempts=7)
            resp = await client.get("/v1/webhooks", headers=auth_headers(key))
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]) == 2
            assert all(d["merchant_id"] == mid for d in data["data"])
            print("\u2713 Webhook list with deliveries")
        finally:
            await cleanup_test_webhook_data(mid)

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            await insert_webhook_delivery(mid, "invoice.created", "delivered")
            await insert_webhook_delivery(mid, "invoice.paid", "failed", attempts=7)
            resp = await client.get("/v1/webhooks?status=failed", headers=auth_headers(key))
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["status"] == "failed"
            print("\u2713 Webhook list filter by status")
        finally:
            await cleanup_test_webhook_data(mid)

    @pytest.mark.asyncio
    async def test_list_invalid_status(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/webhooks?status=bogus", headers=auth_headers(key))
        assert resp.status_code == 400
        print("\u2713 Webhook list invalid status \u2192 400")

    @pytest.mark.asyncio
    async def test_list_pagination(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            ids = []
            for i in range(3):
                did = await insert_webhook_delivery(mid, f"test.event{i}", "delivered")
                ids.append(did)
            resp = await client.get("/v1/webhooks?limit=2", headers=auth_headers(key))
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]) == 2
            assert data["has_more"] is True
            print("\u2713 Webhook list pagination")
        finally:
            await cleanup_test_webhook_data(mid)


class TestWebhookDetail:
    """GET /v1/webhooks/{id} — single delivery."""

    @pytest.mark.asyncio
    async def test_get_delivery(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            did = await insert_webhook_delivery(mid, "invoice.paid", "delivered", response_code=200)
            resp = await client.get(f"/v1/webhooks/{did}", headers=auth_headers(key))
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == did
            assert data["event_type"] == "invoice.paid"
            assert data["status"] == "delivered"
            assert data["response_code"] == 200
            print("\u2713 Webhook get detail")
        finally:
            await cleanup_test_webhook_data(mid)

    @pytest.mark.asyncio
    async def test_get_not_found(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/webhooks/{fake_id}", headers=auth_headers(key))
        assert resp.status_code == 404
        print("\u2713 Webhook get not found \u2192 404")

    @pytest.mark.asyncio
    async def test_get_invalid_id(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/webhooks/not-a-uuid", headers=auth_headers(key))
        assert resp.status_code == 400
        print("\u2713 Webhook get invalid ID \u2192 400")


class TestWebhookRetry:
    """POST /v1/webhooks/{id}/retry — retry failed delivery."""

    @pytest.mark.asyncio
    async def test_retry_invalid_id(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.post("/v1/webhooks/not-a-uuid/retry", headers=auth_headers(key))
        assert resp.status_code == 400
        print("\u2713 Webhook retry invalid ID \u2192 400")

    @pytest.mark.asyncio
    async def test_retry_not_found(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        fake_id = str(uuid.uuid4())
        resp = await client.post(f"/v1/webhooks/{fake_id}/retry", headers=auth_headers(key))
        assert resp.status_code == 404
        print("\u2713 Webhook retry not found \u2192 404")


# ═════════════════════════════════════════════════════════════════════════════
#  DLQ ENDPOINTS (merchant-facing)
# ═════════════════════════════════════════════════════════════════════════════


class TestDLQList:
    """GET /v1/webhooks/dead-letters — list DLQ entries."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/webhooks/dead-letters", headers=auth_headers(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["has_more"] is False
        print("\u2713 DLQ list empty")

    @pytest.mark.asyncio
    async def test_list_with_entries(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            did = await insert_webhook_delivery(mid, "invoice.expired", "dead_lettered", attempts=7)
            await insert_dlq_entry(mid, did, "invoice.expired")
            resp = await client.get("/v1/webhooks/dead-letters", headers=auth_headers(key))
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["data"]) == 1
            entry = data["data"][0]
            assert entry["event_type"] == "invoice.expired"
            assert entry["resolved"] is False
            assert "connection refused" in entry["last_error"]
            print("\u2713 DLQ list with entries")
        finally:
            await cleanup_test_webhook_data(mid)

    @pytest.mark.asyncio
    async def test_list_filter_resolved(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            did1 = await insert_webhook_delivery(mid, "invoice.paid", "dead_lettered", attempts=7)
            did2 = await insert_webhook_delivery(mid, "invoice.expired", "dead_lettered", attempts=7)
            await insert_dlq_entry(mid, did1, "invoice.paid", resolved=False)
            await insert_dlq_entry(mid, did2, "invoice.expired", resolved=True)

            resp_unresolved = await client.get(
                "/v1/webhooks/dead-letters?resolved=false",
                headers=auth_headers(key),
            )
            assert resp_unresolved.status_code == 200
            assert len(resp_unresolved.json()["data"]) == 1

            resp_resolved = await client.get(
                "/v1/webhooks/dead-letters?resolved=true",
                headers=auth_headers(key),
            )
            assert resp_resolved.status_code == 200
            assert len(resp_resolved.json()["data"]) == 1
            print("\u2713 DLQ list filter by resolved")
        finally:
            await cleanup_test_webhook_data(mid)


class TestDLQRetry:
    """POST /v1/webhooks/dead-letters/{id}/retry — retry DLQ entry."""

    @pytest.mark.asyncio
    async def test_retry_not_found(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/webhooks/dead-letters/{fake_id}/retry",
            headers=auth_headers(key),
        )
        assert resp.status_code == 404
        print("\u2713 DLQ retry not found \u2192 404")

    @pytest.mark.asyncio
    async def test_retry_already_resolved(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        mid = fresh_merchant["merchant_id"]
        try:
            did = await insert_webhook_delivery(mid, "invoice.paid", "dead_lettered", attempts=7)
            dlq_id = await insert_dlq_entry(mid, did, "invoice.paid", resolved=True)
            resp = await client.post(
                f"/v1/webhooks/dead-letters/{dlq_id}/retry",
                headers=auth_headers(key),
            )
            assert resp.status_code == 409
            assert "resolved" in resp.json()["detail"].lower()
            print("\u2713 DLQ retry already resolved \u2192 409")
        finally:
            await cleanup_test_webhook_data(mid)


# ═════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════


class TestAdminMe:
    """GET /v1/admin/me — admin status check."""

    @pytest.mark.asyncio
    async def test_admin_me(self, client):
        resp = await client.get("/v1/admin/me", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_admin"] is True
        assert data["merchant_id"] == ADMIN_MERCHANT_ID
        print("\u2713 Admin /me")

    @pytest.mark.asyncio
    async def test_admin_me_non_admin(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/admin/me", headers=auth_headers(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_admin"] is False
        print("\u2713 Admin /me non-admin")

    @pytest.mark.asyncio
    async def test_admin_me_no_auth(self, client):
        resp = await client.get("/v1/admin/me")
        assert resp.status_code == 401
        print("\u2713 Admin /me no auth \u2192 401")


class TestAdminMerchants:
    """GET /v1/admin/merchants — list all merchants."""

    @pytest.mark.asyncio
    async def test_list_merchants(self, client):
        resp = await client.get("/v1/admin/merchants", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        data = resp.json()
        assert "merchants" in data
        assert isinstance(data["merchants"], list)
        assert len(data["merchants"]) >= 1
        print(f"\u2713 Admin merchants list: {len(data['merchants'])} merchants")

    @pytest.mark.asyncio
    async def test_list_merchants_non_admin(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/admin/merchants", headers=auth_headers(key))
        assert resp.status_code == 403
        print("\u2713 Admin merchants non-admin \u2192 403")


class TestAdminStats:
    """GET /v1/admin/stats — global statistics."""

    @pytest.mark.asyncio
    async def test_stats(self, client):
        resp = await client.get("/v1/admin/stats", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        data = resp.json()
        assert "merchants_total" in data
        assert "invoices_total" in data
        assert "payments_total" in data
        print("\u2713 Admin stats")

    @pytest.mark.asyncio
    async def test_stats_non_admin(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.get("/v1/admin/stats", headers=auth_headers(key))
        assert resp.status_code == 403
        print("\u2713 Admin stats non-admin \u2192 403")


class TestAdminHealth:
    """GET /v1/admin/health — detailed system health."""

    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/v1/admin/health", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        data = resp.json()
        assert "database" in data
        assert "redis" in data
        print("\u2713 Admin health")


class TestAdminDLQ:
    """GET /v1/admin/dlq — global DLQ view."""

    @pytest.mark.asyncio
    async def test_dlq_list(self, client):
        resp = await client.get("/v1/admin/dlq", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)
        print("\u2713 Admin DLQ list")


class TestAdminToggle:
    """POST /v1/admin/merchants/{id}/toggle — activate/deactivate."""

    @pytest.mark.asyncio
    async def test_toggle_merchant(self, client, fresh_merchant):
        mid = fresh_merchant["merchant_id"]
        key = fresh_merchant["api_key_live"]

        # Deactivate
        resp = await client.post(
            f"/v1/admin/merchants/{mid}/toggle",
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp.status_code == 200
        assert "deactivated" in resp.json()["message"].lower() or "toggled" in resp.json()["message"].lower()

        # Verify merchant can't auth anymore
        resp_me = await client.get("/v1/merchants/me", headers=auth_headers(key))
        assert resp_me.status_code == 401

        # Re-activate
        resp2 = await client.post(
            f"/v1/admin/merchants/{mid}/toggle",
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp2.status_code == 200

        # Verify merchant can auth again
        resp_me2 = await client.get("/v1/merchants/me", headers=auth_headers(key))
        assert resp_me2.status_code == 200
        print("\u2713 Admin toggle merchant (deactivate \u2192 reactivate)")

    @pytest.mark.asyncio
    async def test_toggle_not_found(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/admin/merchants/{fake_id}/toggle",
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp.status_code == 404
        print("\u2713 Admin toggle not found \u2192 404")


class TestAdminTriggerRenewal:
    """POST /v1/admin/trigger-renewal."""

    @pytest.mark.asyncio
    async def test_trigger_renewal(self, client):
        resp = await client.post(
            "/v1/admin/trigger-renewal",
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        print("\u2713 Admin trigger renewal")

    @pytest.mark.asyncio
    async def test_trigger_renewal_non_admin(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        resp = await client.post("/v1/admin/trigger-renewal", headers=auth_headers(key))
        assert resp.status_code == 403
        print("\u2713 Admin trigger renewal non-admin \u2192 403")


# ═════════════════════════════════════════════════════════════════════════════
#  AUTH SIGNATURE (error paths only — full flow needs Monero wallet)
# ═════════════════════════════════════════════════════════════════════════════


class TestAuthNonce:
    """POST /v1/auth/nonce — request authentication nonce."""

    @pytest.mark.asyncio
    async def test_nonce_invalid_address_short(self, client):
        resp = await client.post("/v1/auth/nonce", json={"address": "4" + "a" * 50})
        assert resp.status_code == 422
        print("\u2713 Auth nonce short address \u2192 422")

    @pytest.mark.asyncio
    async def test_nonce_invalid_address_wrong_prefix(self, client):
        resp = await client.post("/v1/auth/nonce", json={"address": "5" + "a" * 94})
        assert resp.status_code == 400
        print("\u2713 Auth nonce wrong prefix \u2192 400")

    @pytest.mark.asyncio
    async def test_nonce_unregistered_address(self, client):
        addr = "4" + "b" * 94
        resp = await client.post("/v1/auth/nonce", json={"address": addr})
        assert resp.status_code == 400
        print("\u2713 Auth nonce unregistered address \u2192 400")

    @pytest.mark.asyncio
    async def test_nonce_valid_address(self, client):
        m = await _register_base58_merchant(client)
        addr = m["monero_address"]
        resp = await client.post("/v1/auth/nonce", json={"address": addr})
        assert resp.status_code == 200
        data = resp.json()
        assert "nonce" in data
        assert data["expires_in"] == 300
        print("\u2713 Auth nonce valid address")


class TestAuthVerify:
    """POST /v1/auth/verify — verify signature (error paths)."""

    @pytest.mark.asyncio
    async def test_verify_invalid_address(self, client):
        resp = await client.post(
            "/v1/auth/verify",
            json={
                "address": "5" + "a" * 94,
                "nonce": "test_nonce",
                "signature": "SigV1" + "a" * 80,
            },
        )
        assert resp.status_code == 400
        print("\u2713 Auth verify invalid address \u2192 400")

    @pytest.mark.asyncio
    async def test_verify_invalid_signature_format(self, client):
        m = await _register_base58_merchant(client)
        addr = m["monero_address"]
        resp = await client.post(
            "/v1/auth/verify",
            json={
                "address": addr,
                "nonce": "test_nonce",
                "signature": "not_a_valid_signature",
            },
        )
        assert resp.status_code == 400
        assert "signature" in resp.json()["detail"].lower()
        print("\u2713 Auth verify invalid signature format \u2192 400")

    @pytest.mark.asyncio
    async def test_verify_invalid_nonce(self, client):
        m = await _register_base58_merchant(client)
        addr = m["monero_address"]
        resp = await client.post(
            "/v1/auth/verify",
            json={
                "address": addr,
                "nonce": "nonexistent_nonce_" + uuid.uuid4().hex,
                "signature": "SigV1" + "a" * 80,
            },
        )
        assert resp.status_code == 401
        print("\u2713 Auth verify invalid nonce \u2192 401")


class TestAuthLogout:
    """POST /v1/auth/logout — revoke session."""

    @pytest.mark.asyncio
    async def test_logout_invalid_token(self, client):
        resp = await client.post(
            "/v1/auth/logout",
            json={"session_token": "gbs_" + "f" * 64},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["revoked"] is False
        print("\u2713 Auth logout invalid token \u2192 revoked=false")


# ═════════════════════════════════════════════════════════════════════════════
#  PUBLIC INVOICE ENDPOINT
# ═════════════════════════════════════════════════════════════════════════════


class TestPublicInvoice:
    """GET /v1/invoices/{id}/public — public invoice data."""

    @pytest.mark.asyncio
    async def test_public_invoice(self, client, fresh_merchant):
        key = fresh_merchant["api_key_live"]
        invoice = await create_invoice(client, key, amount_xmr="0.01")
        invoice_id = invoice["id"]

        resp = await client.get(f"/v1/invoices/{invoice_id}/public")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == invoice_id
        assert data["status"] == "pending"
        assert "amount_xmr" in data
        print("\u2713 Public invoice endpoint")

    @pytest.mark.asyncio
    async def test_public_invoice_not_found(self, client):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/invoices/{fake_id}/public")
        assert resp.status_code == 404
        print("\u2713 Public invoice not found \u2192 404")
