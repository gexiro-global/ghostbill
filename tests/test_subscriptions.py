"""GhostBill — Subscription integration tests.

Covers: create, actions (pause/resume/cancel), PATCH (pending changes),
        list/detail, renewal simulation via trigger-renewal endpoint.
Updated for Phase 6B cursor pagination ("data" + "has_more").

Usage:
    cd /root/ghostbill && python3 -m pytest tests/test_subscriptions.py -v
"""

import asyncio
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from tests.conftest import (
    auth_headers,
    db_execute,
    db_fetchrow,
    db_fetch,
    update_invoice_status_db,
)

BASE_URL = "http://127.0.0.1:8013"


# ─── Helpers ──────────────────────────────────────────────────────────


async def _create_customer(client, api_key, ext_id=None):
    payload = {"external_id": ext_id or f"test_{uuid.uuid4().hex[:8]}"}
    resp = await client.post("/v1/customers", json=payload, headers=auth_headers(api_key))
    assert resp.status_code == 201, f"Customer create failed: {resp.text}"
    return resp.json()


async def _create_subscription(client, api_key, customer_id, amount="0.5",
                                interval=30, start_at=None):
    payload = {
        "customer_id": customer_id,
        "amount_xmr": amount,
        "interval_days": interval,
    }
    if start_at:
        payload["start_at"] = start_at
    resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(api_key))
    assert resp.status_code == 201, f"Sub create failed: {resp.text}"
    return resp.json()


async def _trigger_renewal(subscription_id: str | None = None):
    """Call trigger-renewal endpoint."""
    params = {}
    if subscription_id:
        params["subscription_id"] = subscription_id
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as c:
        resp = await c.post("/v1/internal/trigger-renewal", params=params)
    return resp


# ─── Create Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSubscriptionCreate:

    async def test_create_basic(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        assert sub["status"] == "active"
        assert sub["billing_anchor_at"] is not None
        assert sub["has_pending_changes"] is False

    async def test_create_with_future_start(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        payload = {
            "customer_id": cust["id"], "amount_xmr": "1.0",
            "interval_days": 30, "start_at": "2099-01-01T00:00:00Z",
        }
        resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(key))
        assert resp.status_code == 201
        assert resp.json()["payments"] == []

    async def test_create_bad_customer(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        payload = {
            "customer_id": str(uuid.uuid4()), "amount_xmr": "0.5", "interval_days": 30,
        }
        resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(key))
        assert resp.status_code == 404

    async def test_create_invalid_amount(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        payload = {"customer_id": cust["id"], "amount_xmr": "0", "interval_days": 30}
        resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(key))
        assert resp.status_code == 400

    async def test_create_grace_validation(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        payload = {
            "customer_id": cust["id"], "amount_xmr": "0.5",
            "interval_days": 30, "grace_days_soft": 10, "grace_days_hard": 5,
        }
        resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(key))
        assert resp.status_code == 400


# ─── Actions Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSubscriptionActions:

    async def test_pause_active(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.post(f"/v1/subscriptions/{sub['id']}/pause", headers=auth_headers(key))
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    async def test_resume_paused(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        await client.post(f"/v1/subscriptions/{sub['id']}/pause", headers=auth_headers(key))
        resp = await client.post(f"/v1/subscriptions/{sub['id']}/resume", headers=auth_headers(key))
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_cancel_active(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.post(f"/v1/subscriptions/{sub['id']}/cancel", headers=auth_headers(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["cancelled_at"] is not None

    async def test_pause_non_active_fails(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        await client.post(f"/v1/subscriptions/{sub['id']}/pause", headers=auth_headers(key))
        resp = await client.post(f"/v1/subscriptions/{sub['id']}/pause", headers=auth_headers(key))
        assert resp.status_code == 409

    async def test_resume_non_paused_fails(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.post(f"/v1/subscriptions/{sub['id']}/resume", headers=auth_headers(key))
        assert resp.status_code == 409

    async def test_cancel_cancelled_fails(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        await client.post(f"/v1/subscriptions/{sub['id']}/cancel", headers=auth_headers(key))
        resp = await client.post(f"/v1/subscriptions/{sub['id']}/cancel", headers=auth_headers(key))
        assert resp.status_code == 409


# ─── PATCH Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSubscriptionPatch:

    async def test_patch_amount(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"], amount="0.5")
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": "1.0"}, headers=auth_headers(key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount_xmr"] == "0.500000000000"
        assert data["has_pending_changes"] is True
        assert data["pending_changes"]["amount_atomic"] == 1000000000000

    async def test_patch_interval(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"interval_days": 14}, headers=auth_headers(key),
        )
        assert resp.status_code == 200
        assert resp.json()["pending_changes"]["interval_days"] == 14

    async def test_patch_metadata_immediate(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"metadata": {"plan": "pro"}}, headers=auth_headers(key),
        )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["plan"] == "pro"

    async def test_patch_clear_pending(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": "2.0"}, headers=auth_headers(key),
        )
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": None}, headers=auth_headers(key),
        )
        assert resp.status_code == 200
        assert resp.json()["has_pending_changes"] is False

    async def test_patch_cancelled_fails(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        await client.post(f"/v1/subscriptions/{sub['id']}/cancel", headers=auth_headers(key))
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": "1.0"}, headers=auth_headers(key),
        )
        assert resp.status_code == 409

    async def test_patch_paused_allowed(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        await client.post(f"/v1/subscriptions/{sub['id']}/pause", headers=auth_headers(key))
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": "1.0"}, headers=auth_headers(key),
        )
        assert resp.status_code == 200
        assert resp.json()["has_pending_changes"] is True

    async def test_patch_invalid_amount(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": "-1"}, headers=auth_headers(key),
        )
        assert resp.status_code == 400


# ─── Query Tests (updated for cursor pagination) ────────────────────


@pytest.mark.asyncio
class TestSubscriptionQuery:

    async def test_list_subscriptions(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        resp = await client.get("/v1/subscriptions", headers=auth_headers(key))
        assert resp.status_code == 200
        assert "data" in resp.json()
        assert "has_more" in resp.json()

    async def test_list_filter_by_status(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        await _create_subscription(client, key, cust["id"])
        resp = await client.get("/v1/subscriptions?status=active", headers=auth_headers(key))
        assert resp.status_code == 200
        for s in resp.json()["data"]:
            assert s["status"] == "active"

    async def test_get_detail(self, client, test_merchant):
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(client, key, cust["id"])
        resp = await client.get(f"/v1/subscriptions/{sub['id']}", headers=auth_headers(key))
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer"] is not None
        assert "payments" in data
        assert data["billing_anchor_at"] is not None


# ─── Renewal Tests ────────────────────────────────────────────────────
# Strategy: create with future start_at (no first invoice), then set
# next_due_at to past via DB, then trigger renewal. This avoids conflicts
# with existing subscription_payments from the first invoice.


@pytest.mark.asyncio
class TestSubscriptionRenewal:

    async def test_trigger_renewal_single(self, client, test_merchant):
        """Create sub (future start) \u2192 set next_due to past \u2192 trigger \u2192 renewed=1."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        # Future start = no immediate first invoice
        sub = await _create_subscription(
            client, key, cust["id"], amount="0.1", interval=1,
            start_at="2099-01-01T00:00:00Z",
        )
        assert sub["payments"] == [], "Should have no payments with future start"

        # Set next_due to past so renewal picks it up
        sub_id = uuid.UUID(sub["id"])
        await db_execute(
            "UPDATE subscriptions SET next_due_at = NOW() - INTERVAL '1 minute' WHERE id = $1::uuid",
            sub_id,
        )

        resp = await _trigger_renewal(subscription_id=sub["id"])
        assert resp.status_code == 200, f"trigger failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["renewed"] == 1, f"Expected renewed=1, got: {data}"

    async def test_pending_changes_applied_on_renewal(self, client, test_merchant):
        """PATCH amount \u2192 trigger renewal \u2192 verify amount updated."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        # Future start = no first invoice
        sub = await _create_subscription(
            client, key, cust["id"], amount="0.5", interval=1,
            start_at="2099-01-01T00:00:00Z",
        )

        # PATCH: set pending amount
        await client.patch(
            f"/v1/subscriptions/{sub['id']}",
            json={"amount_xmr": "1.0"}, headers=auth_headers(key),
        )

        # Verify current still 0.5, pending set
        detail = await client.get(f"/v1/subscriptions/{sub['id']}", headers=auth_headers(key))
        assert detail.json()["amount_xmr"] == "0.500000000000"
        assert detail.json()["has_pending_changes"] is True

        # Set next_due to past
        sub_id = uuid.UUID(sub["id"])
        await db_execute(
            "UPDATE subscriptions SET next_due_at = NOW() - INTERVAL '1 minute' WHERE id = $1::uuid",
            sub_id,
        )

        # Trigger renewal
        resp = await _trigger_renewal(subscription_id=sub["id"])
        assert resp.status_code == 200, f"trigger failed: {resp.text}"
        data = resp.json()
        assert data["renewed"] == 1, f"Renewal failed: {data}"

        # Verify: amount now 1.0, pending cleared
        detail2 = await client.get(f"/v1/subscriptions/{sub['id']}", headers=auth_headers(key))
        assert detail2.json()["amount_xmr"] == "1.000000000000"
        assert detail2.json()["has_pending_changes"] is False
