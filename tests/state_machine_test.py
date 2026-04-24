"""GhostBill — Invoice state machine tests.

Tests all 7 invoice statuses and their valid/invalid transitions.
Updated for Phase 6B cursor pagination ("data" + "has_more").

Usage:
    cd /root/ghostbill && python3 -m pytest tests/state_machine_test.py -v
"""

import httpx
import pytest

from tests.conftest import (
    auth_headers,
    create_invoice,
    expire_invoice_db,
    get_invoice,
    get_invoice_status_db,
    insert_simulated_payment,
    update_invoice_status_db,
)


@pytest.mark.asyncio
class TestValidTransitions:
    async def test_pending_to_paid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")
        invoice_id = inv["id"]
        assert inv["status"] == "pending"

        await insert_simulated_payment(
            invoice_id, amount_atomic=inv["amount_atomic"], status="confirmed", confirmations=10
        )
        await update_invoice_status_db(invoice_id, "paid")

        inv_after = await get_invoice(client, api_key, invoice_id)
        assert inv_after["status"] == "paid"
        assert await get_invoice_status_db(invoice_id) == "paid"
        print("\u2713 pending \u2192 paid")

    async def test_pending_to_partially_paid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")

        await insert_simulated_payment(inv["id"], amount_atomic=500000000000, status="detected", confirmations=2)
        await update_invoice_status_db(inv["id"], "partially_paid")

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "partially_paid"
        print("\u2713 pending \u2192 partially_paid")

    async def test_pending_to_expired(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")

        await expire_invoice_db(inv["id"])

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "expired"
        print("\u2713 pending \u2192 expired")

    async def test_pending_to_cancelled(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        print("\u2713 pending \u2192 cancelled")

    async def test_partially_paid_to_paid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")

        await insert_simulated_payment(inv["id"], amount_atomic=600000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "partially_paid")

        await insert_simulated_payment(inv["id"], amount_atomic=400000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "paid")

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "paid"
        print("\u2713 partially_paid \u2192 paid")

    async def test_partially_paid_to_overpaid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")

        await insert_simulated_payment(inv["id"], amount_atomic=300000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "partially_paid")

        await insert_simulated_payment(inv["id"], amount_atomic=500000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "overpaid")

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "overpaid"
        print("\u2713 partially_paid \u2192 overpaid")

    async def test_expired_to_late_paid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.2")

        await expire_invoice_db(inv["id"])
        assert await get_invoice_status_db(inv["id"]) == "expired"

        await insert_simulated_payment(inv["id"], amount_atomic=200000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "late_paid")

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "late_paid"
        print("\u2713 expired \u2192 late_paid")


@pytest.mark.asyncio
class TestTerminalStates:
    async def test_paid_is_terminal(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")
        await insert_simulated_payment(inv["id"], amount_atomic=100000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "paid")

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 paid is terminal")

    async def test_cancelled_is_terminal(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")
        await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))

        resp2 = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp2.status_code == 400
        print("\u2713 cancelled is terminal")

    async def test_overpaid_is_terminal(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")
        await insert_simulated_payment(inv["id"], amount_atomic=200000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "overpaid")

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 overpaid is terminal")

    async def test_late_paid_is_terminal(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")
        await expire_invoice_db(inv["id"])
        await insert_simulated_payment(inv["id"], amount_atomic=100000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "late_paid")

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 late_paid is terminal")

    async def test_expired_cannot_be_cancelled(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")
        await expire_invoice_db(inv["id"])

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 expired cannot be cancelled")


@pytest.mark.asyncio
class TestInvalidTransitions:
    async def test_cannot_cancel_with_payments(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")
        await insert_simulated_payment(inv["id"], amount_atomic=100000000000, status="detected", confirmations=0)

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 cannot cancel with payments")

    async def test_partially_paid_cannot_be_cancelled(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")
        await insert_simulated_payment(inv["id"], amount_atomic=300000000000, status="detected", confirmations=2)
        await update_invoice_status_db(inv["id"], "partially_paid")

        resp = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp.status_code == 400
        print("\u2713 partially_paid cannot be cancelled")


@pytest.mark.asyncio
class TestStatusFiltering:
    async def test_filter_by_each_status(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]

        for target in ["pending", "expired", "cancelled"]:
            inv = await create_invoice(client, api_key, amount_xmr="0.01", description=f"Filter: {target}")
            if target == "expired":
                await expire_invoice_db(inv["id"])
            elif target == "cancelled":
                await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))

        for target in ["pending", "expired", "cancelled"]:
            resp = await client.get(
                "/v1/invoices", params={"status": target, "limit": 10}, headers=auth_headers(api_key)
            )
            assert resp.status_code == 200
            assert len(resp.json()["data"]) >= 1
            for inv in resp.json()["data"]:
                assert inv["status"] == target
            print(f"\u2713 Filter '{target}': {len(resp.json()['data'])} found")

    async def test_invalid_status_filter(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.get(
            "/v1/invoices", params={"status": "nonexistent"}, headers=auth_headers(test_merchant["api_key_live"])
        )
        assert resp.status_code == 400
        print("\u2713 Invalid status \u2192 400")
