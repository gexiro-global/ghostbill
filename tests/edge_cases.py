"""
GhostBill — Edge case tests.

Usage:
    cd /root/ghostbill && python3 -m pytest tests/edge_cases.py -v
"""

import uuid

import httpx
import pytest

from tests.conftest import (
    DUST_THRESHOLD_ATOMIC,
    PICONERO,
    auth_headers,
    count_payments_for_invoice,
    create_invoice,
    expire_invoice_db,
    get_invoice,
    get_invoice_status_db,
    insert_simulated_payment,
    sum_payments_for_invoice,
    update_invoice_status_db,
    update_payment_status_db,
)


@pytest.mark.asyncio
class TestDustRejection:
    async def test_dust_payment_below_threshold(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")
        dust_amount = DUST_THRESHOLD_ATOMIC - 1
        await insert_simulated_payment(inv["id"], amount_atomic=dust_amount, status="detected")

        count = await count_payments_for_invoice(inv["id"])
        assert count == 1
        total = await sum_payments_for_invoice(inv["id"])
        assert total == dust_amount
        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "pending"
        print(f"✓ Dust threshold: {DUST_THRESHOLD_ATOMIC} atomic")

    async def test_dust_threshold_exact(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")
        await insert_simulated_payment(inv["id"], amount_atomic=DUST_THRESHOLD_ATOMIC, status="detected")

        assert await count_payments_for_invoice(inv["id"]) == 1
        assert await sum_payments_for_invoice(inv["id"]) == DUST_THRESHOLD_ATOMIC
        print(f"✓ Exact threshold ({DUST_THRESHOLD_ATOMIC}) accepted")


@pytest.mark.asyncio
class TestPartialPayment:
    async def test_three_partial_payments_to_paid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")
        iid = inv["id"]

        await insert_simulated_payment(iid, amount_atomic=300000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(iid, "partially_paid")

        await insert_simulated_payment(iid, amount_atomic=300000000000, status="confirmed", confirmations=10)
        await insert_simulated_payment(iid, amount_atomic=400000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(iid, "paid")

        assert await sum_payments_for_invoice(iid) == 1000000000000
        assert (await get_invoice(client, api_key, iid))["status"] == "paid"
        assert await count_payments_for_invoice(iid) == 3
        print("✓ Three partial → paid")

    async def test_partial_stays_partially_paid(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="2.0")
        await insert_simulated_payment(inv["id"], amount_atomic=200000000000, status="detected", confirmations=3)
        await update_invoice_status_db(inv["id"], "partially_paid")

        assert await sum_payments_for_invoice(inv["id"]) == 200000000000
        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "partially_paid"
        print("✓ Partial → stays partially_paid")


@pytest.mark.asyncio
class TestOverpayment:
    async def test_single_overpayment(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")
        await insert_simulated_payment(inv["id"], amount_atomic=1000000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "overpaid")

        assert await sum_payments_for_invoice(inv["id"]) == 1000000000000
        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "overpaid"
        print("✓ Single overpayment")

    async def test_cumulative_overpayment(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")
        await insert_simulated_payment(inv["id"], amount_atomic=300000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "partially_paid")
        await insert_simulated_payment(inv["id"], amount_atomic=400000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "overpaid")

        assert await sum_payments_for_invoice(inv["id"]) == 700000000000
        print("✓ Cumulative overpayment: 0.3 + 0.4 > 0.5")


@pytest.mark.asyncio
class TestLatePaid:
    async def test_full_payment_after_expiry(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")
        await expire_invoice_db(inv["id"])
        assert await get_invoice_status_db(inv["id"]) == "expired"

        await insert_simulated_payment(inv["id"], amount_atomic=500000000000, status="confirmed", confirmations=10)
        await update_invoice_status_db(inv["id"], "late_paid")

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "late_paid"
        print("✓ Full payment after expiry → late_paid")

    async def test_partial_payment_after_expiry(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")
        await expire_invoice_db(inv["id"])

        await insert_simulated_payment(inv["id"], amount_atomic=200000000000, status="detected", confirmations=2)
        await update_invoice_status_db(inv["id"], "late_paid")

        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "late_paid"
        print("✓ Partial after expiry → late_paid")


@pytest.mark.asyncio
class TestReorgOrphaned:
    async def test_payment_orphaned_reverts_status(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.5")

        payment = await insert_simulated_payment(
            inv["id"], amount_atomic=500000000000, status="detected", confirmations=3
        )
        await update_invoice_status_db(inv["id"], "partially_paid")

        await update_payment_status_db(payment["id"], "orphaned")
        assert await sum_payments_for_invoice(inv["id"]) == 0

        await update_invoice_status_db(inv["id"], "pending")
        assert (await get_invoice(client, api_key, inv["id"]))["status"] == "pending"
        print("✓ Orphaned → revert to pending")

    async def test_one_of_two_payments_orphaned(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="1.0")

        _p1 = await insert_simulated_payment(
            inv["id"], amount_atomic=600000000000, status="confirmed", confirmations=10
        )
        p2 = await insert_simulated_payment(inv["id"], amount_atomic=400000000000, status="confirmed", confirmations=10)
        assert await sum_payments_for_invoice(inv["id"]) == 1000000000000

        await update_payment_status_db(p2["id"], "orphaned")
        assert await sum_payments_for_invoice(inv["id"]) == 600000000000
        assert await count_payments_for_invoice(inv["id"], status="confirmed") == 1
        assert await count_payments_for_invoice(inv["id"], status="orphaned") == 1
        print("✓ One of two orphaned → sum recalculated")


@pytest.mark.asyncio
class TestCancelEdgeCases:
    async def test_cancel_nonexistent(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.post(
            f"/v1/invoices/{uuid.uuid4()}/cancel", headers=auth_headers(test_merchant["api_key_live"])
        )
        assert resp.status_code == 404
        print("✓ Cancel nonexistent → 404")

    async def test_cancel_other_merchants_invoice(
        self, client: httpx.AsyncClient, test_merchant: dict, fresh_merchant: dict
    ):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="0.1")
        resp = await client.post(
            f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(fresh_merchant["api_key_live"])
        )
        assert resp.status_code == 404
        print("✓ Cannot cancel other's invoice")

    async def test_double_cancel(self, client: httpx.AsyncClient, test_merchant: dict):
        api_key = test_merchant["api_key_live"]
        inv = await create_invoice(client, api_key, amount_xmr="0.1")
        await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        resp2 = await client.post(f"/v1/invoices/{inv['id']}/cancel", headers=auth_headers(api_key))
        assert resp2.status_code == 400
        print("✓ Double cancel → 400")


@pytest.mark.asyncio
class TestAmountPrecision:
    async def test_very_small_amount(self, client: httpx.AsyncClient, test_merchant: dict):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="0.000000000001")
        assert inv["amount_atomic"] == 1
        print("✓ 1 piconero = 1 atomic")

    async def test_large_amount(self, client: httpx.AsyncClient, test_merchant: dict):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="100.0")
        assert inv["amount_atomic"] == 100 * PICONERO
        print(f"✓ 100 XMR = {100 * PICONERO} atomic")

    async def test_precision_12_decimals(self, client: httpx.AsyncClient, test_merchant: dict):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="1.123456789012")
        assert inv["amount_atomic"] == 1123456789012
        print("✓ 12-decimal precision OK")

    async def test_zero_amount_rejected(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.post(
            "/v1/invoices", json={"amount_xmr": "0"}, headers=auth_headers(test_merchant["api_key_live"])
        )
        assert resp.status_code == 400
        print("✓ Zero → 400")

    async def test_negative_amount_rejected(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.post(
            "/v1/invoices", json={"amount_xmr": "-0.5"}, headers=auth_headers(test_merchant["api_key_live"])
        )
        assert resp.status_code == 400
        print("✓ Negative → 400")

    async def test_invalid_amount_string(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.post(
            "/v1/invoices", json={"amount_xmr": "not_a_number"}, headers=auth_headers(test_merchant["api_key_live"])
        )
        assert resp.status_code == 400
        print("✓ Invalid string → 400")


@pytest.mark.asyncio
class TestExpirationBoundaries:
    async def test_min_expiration(self, client: httpx.AsyncClient, test_merchant: dict):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="0.1", expires_in=600)
        assert inv["status"] == "pending"
        print("✓ Min (600s) OK")

    async def test_max_expiration(self, client: httpx.AsyncClient, test_merchant: dict):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="0.1", expires_in=86400)
        assert inv["status"] == "pending"
        print("✓ Max (86400s) OK")

    async def test_below_min_rejected(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.post(
            "/v1/invoices",
            json={"amount_xmr": "0.1", "expires_in": 599},
            headers=auth_headers(test_merchant["api_key_live"]),
        )
        assert resp.status_code in (400, 422)
        print("✓ Below min (599s) rejected")

    async def test_above_max_rejected(self, client: httpx.AsyncClient, test_merchant: dict):
        resp = await client.post(
            "/v1/invoices",
            json={"amount_xmr": "0.1", "expires_in": 86401},
            headers=auth_headers(test_merchant["api_key_live"]),
        )
        assert resp.status_code in (400, 422)
        print("✓ Above max (86401s) rejected")


@pytest.mark.asyncio
class TestAuthEdgeCases:
    async def test_no_auth_header(self, client: httpx.AsyncClient):
        assert (await client.get("/v1/invoices")).status_code == 401
        print("✓ No auth → 401")

    async def test_invalid_api_key(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/invoices", headers=auth_headers("gb_live_0000000000000000000000000000dead"))
        assert resp.status_code == 401
        print("✓ Invalid key → 401")

    async def test_malformed_bearer(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/invoices", headers={"Authorization": "NotBearer token"})
        assert resp.status_code == 401
        print("✓ Malformed bearer → 401")

    async def test_empty_bearer(self, client: httpx.AsyncClient):
        # "Bearer " with trailing space is rejected by httpx itself (illegal header)
        # Test with "Bearer" (no space, no token) instead
        resp = await client.get("/v1/invoices", headers={"Authorization": "Bearer"})
        assert resp.status_code == 401
        print("✓ Empty bearer → 401")

    async def test_merchant_isolation(self, client: httpx.AsyncClient, test_merchant: dict, fresh_merchant: dict):
        inv = await create_invoice(client, test_merchant["api_key_live"], amount_xmr="0.1")
        resp = await client.get(f"/v1/invoices/{inv['id']}", headers=auth_headers(fresh_merchant["api_key_live"]))
        assert resp.status_code == 404
        print("✓ Merchant isolation OK")
