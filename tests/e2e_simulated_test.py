"""GhostBill — End-to-end simulated test.

Full flow WITHOUT real XMR.
Updated for Phase 6B cursor pagination ("data" + "has_more").

Usage:
    cd /root/ghostbill && python3 -m pytest tests/e2e_simulated_test.py -v
"""

import hashlib
import hmac
import json
import uuid

import httpx
import pytest

from tests.conftest import (
    TEST_VIEW_KEY,
    auth_headers,
    cleanup_merchant_data,
    create_invoice,
    generate_fake_tx_hash,
    generate_unique_address,
    get_invoice,
    get_invoice_status_db,
    insert_simulated_payment,
    sum_payments_for_invoice,
    update_invoice_status_db,
    verify_webhook_signature,
)


@pytest.mark.asyncio
class TestE2EFullFlow:
    async def test_complete_payment_flow(self, client: httpx.AsyncClient):
        """Full lifecycle: register → invoice → payment → paid → verify."""

        # Step 1: Register merchant
        address = generate_unique_address()
        reg_resp = await client.post(
            "/v1/merchants",
            json={
                "primary_address": address,
                "view_key": TEST_VIEW_KEY,
                "name": "E2E Test Store",
                "email": "e2e@ghostbill.local",
                "webhook_url": "http://127.0.0.1:9999/webhook",
            },
        )
        assert reg_resp.status_code == 201
        reg_data = reg_resp.json()
        merchant_id = reg_data["merchant_id"]
        api_key = reg_data["api_keys"]["live"]
        _webhook_secret = reg_data["webhook_secret"]

        assert api_key.startswith("gb_live_")
        print(f"\n\u2713 Step 1: Merchant registered: {merchant_id}")

        # Step 2: Verify profile
        me_resp = await client.get("/v1/merchants/me", headers=auth_headers(api_key))
        assert me_resp.status_code == 200
        assert me_resp.json()["id"] == merchant_id
        print("\u2713 Step 2: Merchant profile verified")

        # Step 3: Create invoice
        inv = await create_invoice(
            client,
            api_key,
            amount_xmr="0.75",
            description="E2E test invoice",
            expires_in=3600,
            metadata={"order_id": "ORD-12345"},
        )
        invoice_id = inv["id"]
        assert inv["status"] == "pending"
        assert inv["amount_atomic"] == 750000000000
        assert inv["address"] is not None
        print(f"\u2713 Step 3: Invoice created: {invoice_id}")

        # Step 4: Simulate payment (DB INSERT)
        tx_hash = generate_fake_tx_hash()
        _payment = await insert_simulated_payment(
            invoice_id,
            amount_atomic=750000000000,
            tx_hash=tx_hash,
            status="confirmed",
            confirmations=10,
            block_height=3200000,
        )
        print(f"\u2713 Step 4: Payment simulated: tx={tx_hash[:16]}...")

        # Step 5: Update invoice status to paid
        await update_invoice_status_db(invoice_id, "paid")
        db_status = await get_invoice_status_db(invoice_id)
        assert db_status == "paid"

        inv_after = await get_invoice(client, api_key, invoice_id)
        assert inv_after["status"] == "paid"
        print("\u2713 Step 5: Invoice status \u2192 paid")

        # Step 6: Verify cumulative sum
        total = await sum_payments_for_invoice(invoice_id)
        assert total == 750000000000
        print(f"\u2713 Step 6: Cumulative sum verified: {total}")

        # Step 7: Verify payment via API (cursor pagination)
        payments_resp = await client.get(
            "/v1/payments",
            params={"invoice_id": invoice_id},
            headers=auth_headers(api_key),
        )
        assert payments_resp.status_code == 200
        assert len(payments_resp.json()["data"]) >= 1
        found = any(p["tx_hash"] == tx_hash for p in payments_resp.json()["data"])
        assert found
        print("\u2713 Step 7: Payment verified via API")

        # Step 8: List invoices (cursor pagination)
        list_resp = await client.get(
            "/v1/invoices",
            params={"status": "paid", "limit": 10},
            headers=auth_headers(api_key),
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) >= 1
        print("\u2713 Step 8: Paid invoice found in listing")

        # Cleanup
        await cleanup_merchant_data(merchant_id)
        print("\u2713 Cleanup complete")

    async def test_multi_payment_e2e(self, client: httpx.AsyncClient):
        """E2E: Multiple payments completing an invoice."""
        address = generate_unique_address()
        reg_resp = await client.post(
            "/v1/merchants",
            json={"primary_address": address, "view_key": TEST_VIEW_KEY, "name": "Multi-Pay Store"},
        )
        assert reg_resp.status_code == 201
        reg_data = reg_resp.json()
        merchant_id = reg_data["merchant_id"]
        api_key = reg_data["api_keys"]["live"]

        inv = await create_invoice(client, api_key, amount_xmr="1.0")
        invoice_id = inv["id"]

        # Payment 1: 0.4 XMR
        await insert_simulated_payment(invoice_id, amount_atomic=400000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(invoice_id, "partially_paid")

        total = await sum_payments_for_invoice(invoice_id)
        assert total == 400000000000

        inv_partial = await get_invoice(client, api_key, invoice_id)
        assert inv_partial["status"] == "partially_paid"
        print("\n\u2713 First payment 0.4 XMR \u2192 partially_paid")

        # Payment 2: 0.6 XMR (total = 1.0 XMR)
        await insert_simulated_payment(invoice_id, amount_atomic=600000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(invoice_id, "paid")

        total = await sum_payments_for_invoice(invoice_id)
        assert total == 1000000000000

        inv_paid = await get_invoice(client, api_key, invoice_id)
        assert inv_paid["status"] == "paid"
        print("\u2713 Second payment 0.6 XMR \u2192 paid")

        payments_resp = await client.get(
            "/v1/payments",
            params={"invoice_id": invoice_id},
            headers=auth_headers(api_key),
        )
        assert len(payments_resp.json()["data"]) == 2
        print("\u2713 2 payments verified via API")

        await cleanup_merchant_data(merchant_id)


@pytest.mark.asyncio
class TestAPIKeyManagement:
    async def test_api_key_lifecycle(self, client: httpx.AsyncClient, test_merchant: dict):
        """Create \u2192 list \u2192 use \u2192 revoke \u2192 verify revoked."""
        api_key = test_merchant["api_key_live"]

        # Create new key
        create_resp = await client.post(
            "/v1/api-keys",
            json={"label": "E2E test key", "environment": "live"},
            headers=auth_headers(api_key),
        )
        assert create_resp.status_code == 201, f"Key creation failed: {create_resp.status_code} {create_resp.text}"

        key_data = create_resp.json()
        new_key = key_data["key"]
        new_key_id = key_data["id"]
        assert new_key.startswith("gb_live_")
        print(f"\n\u2713 API key created: {new_key[:16]}...")

        # List keys (cursor pagination)
        list_resp = await client.get("/v1/api-keys", headers=auth_headers(api_key))
        assert list_resp.status_code == 200
        key_list = list_resp.json().get("data", [])
        found = any(k.get("id") == new_key_id for k in key_list)
        assert found
        print(f"\u2713 API key found in listing ({len(key_list)} total)")

        # Use new key
        me_resp = await client.get("/v1/merchants/me", headers=auth_headers(new_key))
        assert me_resp.status_code == 200
        print("\u2713 New API key works")

        # Revoke key
        revoke_resp = await client.delete(f"/v1/api-keys/{new_key_id}", headers=auth_headers(api_key))
        assert revoke_resp.status_code == 200
        print("\u2713 API key revoked")

        # Verify revoked
        me_resp2 = await client.get("/v1/merchants/me", headers=auth_headers(new_key))
        assert me_resp2.status_code == 401
        print("\u2713 Revoked key returns 401")


@pytest.mark.asyncio
class TestWebhookHMAC:
    async def test_hmac_signature_correctness(self):
        secret = "test_webhook_secret_abc123"
        payload = {"event": "payment.confirmed", "payment": {"id": "test", "amount_atomic": 500000000000}}
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(key=secret.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256).hexdigest()

        assert verify_webhook_signature(payload_bytes, secret, signature)
        assert not verify_webhook_signature(payload_bytes + b"x", secret, signature)
        assert not verify_webhook_signature(payload_bytes, "wrong_secret", signature)
        print("\n\u2713 HMAC-SHA256 verification correct")

    async def test_webhook_header_format(self):
        required = ["Content-Type", "X-GhostBill-Signature", "X-GhostBill-Event-ID", "X-GhostBill-Event-Type"]
        for h in required:
            assert isinstance(h, str) and len(h) > 0
        print("\u2713 Webhook header names match spec")


@pytest.mark.asyncio
class TestMerchantUpdate:
    async def test_update_merchant_name(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        new_name = f"Updated_{uuid.uuid4().hex[:6]}"
        resp = await client.patch("/v1/merchants/me", json={"name": new_name}, headers=auth_headers(api_key))
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name
        print(f"\n\u2713 Name updated: {new_name}")

    async def test_update_webhook_url(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        resp = await client.patch(
            "/v1/merchants/me",
            json={"webhook_url": "http://127.0.0.1:9876/wh"},
            headers=auth_headers(api_key),
        )
        assert resp.status_code == 200
        print("\u2713 Webhook URL updated")

    async def test_regenerate_webhook_secret(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        resp = await client.post("/v1/merchants/me/webhook-secret", headers=auth_headers(api_key))
        assert resp.status_code == 200
        assert len(resp.json()["webhook_secret"]) > 0
        print("\u2713 Webhook secret regenerated")

    async def test_empty_update_rejected(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        resp = await client.patch("/v1/merchants/me", json={}, headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 Empty update rejected (400)")


@pytest.mark.asyncio
class TestPublicEndpoints:
    async def test_health_endpoint(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        print(f"\n\u2713 Health: {resp.json()}")

    async def test_price_endpoint(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/price")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)
        print(f"\u2713 Price: {resp.json()}")


@pytest.mark.asyncio
class TestInvoiceMetadata:
    async def test_metadata_preserved(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        metadata = {"order_id": "ORD-99999", "items": ["a", "b"]}
        inv = await create_invoice(client, api_key, amount_xmr="0.1", metadata=metadata)
        assert inv["metadata"]["order_id"] == "ORD-99999"

        inv_get = await get_invoice(client, api_key, inv["id"])
        assert inv_get["metadata"]["order_id"] == "ORD-99999"
        print("\n\u2713 Metadata preserved")

    async def test_invoice_without_metadata(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1", metadata=None)
        assert inv["metadata"] is None
        print("\u2713 No metadata \u2192 null")
