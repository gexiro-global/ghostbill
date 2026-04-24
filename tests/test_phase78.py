"""GhostBill — Phase 7-8 integration tests.

Covers:
    Phase 7A: Analytics endpoints (revenue, invoices, subscriptions)
    Phase 7B: SSE endpoint existence
    Phase 8A: Trial periods (create, cancel, validation)
    Phase 8B: Pre-payment (plans config, prepay invoice, validation)

Usage:
    cd /root/ghostbill && python3 -m pytest tests/test_phase78.py -v
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from tests.conftest import (
    auth_headers,
    db_execute,
    db_fetchrow,
    db_fetch,
)

BASE_URL = "http://127.0.0.1:8013"


# ── Helpers ───────────────────────────────────────────────────────────


async def _create_customer(client, api_key, ext_id=None):
    payload = {"external_id": ext_id or f"test_{uuid.uuid4().hex[:8]}"}
    resp = await client.post("/v1/customers", json=payload, headers=auth_headers(api_key))
    assert resp.status_code == 201, f"Customer create failed: {resp.text}"
    return resp.json()


async def _create_subscription(client, api_key, customer_id, amount="0.5",
                                interval=30, start_at=None, trial_days=None):
    payload = {
        "customer_id": customer_id,
        "amount_xmr": amount,
        "interval_days": interval,
    }
    if start_at:
        payload["start_at"] = start_at
    if trial_days is not None:
        payload["trial_days"] = trial_days
    resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(api_key))
    assert resp.status_code == 201, f"Sub create failed: {resp.text}"
    return resp.json()


# =============================================================
# Phase 7A: Analytics
# =============================================================


@pytest.mark.asyncio
class TestAnalytics:

    async def test_revenue_unauthenticated(self, client):
        """Analytics endpoints require auth."""
        resp = await client.get("/v1/analytics/revenue")
        assert resp.status_code in (401, 403)

    async def test_revenue_authenticated(self, client, test_merchant):
        """Revenue endpoint returns valid structure."""
        key = test_merchant["api_key_live"]
        resp = await client.get(
            "/v1/analytics/revenue?period=7d",
            headers=auth_headers(key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or "daily" in data or isinstance(data, list) or "revenue" in data

    async def test_invoice_stats(self, client, test_merchant):
        """Invoice stats endpoint returns valid structure."""
        key = test_merchant["api_key_live"]
        resp = await client.get(
            "/v1/analytics/invoices?period_days=30",
            headers=auth_headers(key),
        )
        assert resp.status_code == 200

    async def test_subscription_metrics(self, client, test_merchant):
        """Subscription metrics endpoint returns valid structure."""
        key = test_merchant["api_key_live"]
        resp = await client.get(
            "/v1/analytics/subscriptions",
            headers=auth_headers(key),
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have MRR and active count fields
        assert any(k in data for k in ("active_count", "mrr", "mrr_atomic", "active"))


# =============================================================
# Phase 7B: SSE
# =============================================================


@pytest.mark.asyncio
class TestSSE:

    async def test_sse_endpoint_nonexistent_invoice(self, client):
        """SSE endpoint returns 404 for non-existent invoice."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/invoices/{fake_id}/events")
        assert resp.status_code == 404

    async def test_public_endpoint_nonexistent_invoice(self, client):
        """Public invoice endpoint returns 404 for non-existent invoice."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/invoices/{fake_id}/public")
        assert resp.status_code == 404


# =============================================================
# Phase 8A: Trial Periods
# =============================================================


@pytest.mark.asyncio
class TestTrialPeriods:

    async def test_create_with_trial(self, client, test_merchant):
        """Subscription with trial_days starts in trialing status."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(
            client, key, cust["id"], trial_days=14,
        )
        assert sub["status"] == "trialing"
        assert sub["trial_days"] == 14
        assert sub["trial_end_at"] is not None
        # No payments during trial
        assert len(sub.get("payments", [])) == 0

    async def test_trial_cancel(self, client, test_merchant):
        """Trialing subscription can be cancelled."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(
            client, key, cust["id"], trial_days=7,
        )
        assert sub["status"] == "trialing"

        resp = await client.post(
            f"/v1/subscriptions/{sub['id']}/cancel",
            json={}, headers=auth_headers(key),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_trial_pause_fails(self, client, test_merchant):
        """Trialing subscription cannot be paused (only active can)."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        sub = await _create_subscription(
            client, key, cust["id"], trial_days=7,
        )
        resp = await client.post(
            f"/v1/subscriptions/{sub['id']}/pause",
            json={}, headers=auth_headers(key),
        )
        assert resp.status_code == 409

    async def test_trial_days_too_high(self, client, test_merchant):
        """trial_days > 365 rejected."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        payload = {
            "customer_id": cust["id"],
            "amount_xmr": "0.5",
            "interval_days": 30,
            "trial_days": 999,
        }
        resp = await client.post(
            "/v1/subscriptions", json=payload, headers=auth_headers(key),
        )
        assert resp.status_code == 422  # Pydantic validation

    async def test_trial_days_zero(self, client, test_merchant):
        """trial_days=0 rejected (min 1)."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        payload = {
            "customer_id": cust["id"],
            "amount_xmr": "0.5",
            "interval_days": 30,
            "trial_days": 0,
        }
        resp = await client.post(
            "/v1/subscriptions", json=payload, headers=auth_headers(key),
        )
        assert resp.status_code == 422  # Pydantic validation


# =============================================================
# Phase 8B: Pre-Payment
# =============================================================


@pytest.mark.asyncio
class TestPrepay:

    async def test_prepay_no_plans_configured(self, client, test_merchant):
        """Prepay fails when merchant has no prepay_plans."""
        key = test_merchant["api_key_live"]
        cust = await _create_customer(client, key)
        # Use future start to avoid first-invoice collision
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        sub = await _create_subscription(
            client, key, cust["id"], start_at=future,
        )
        resp = await client.post(
            f"/v1/subscriptions/{sub['id']}/prepay",
            json={"periods": 3},
            headers=auth_headers(key),
        )
        assert resp.status_code == 400
        assert "plan" in resp.json()["detail"].lower() or "configure" in resp.json()["detail"].lower()

    async def test_configure_prepay_plans(self, client, fresh_merchant):
        """Merchant can set prepay_plans via PATCH."""
        key = fresh_merchant["api_key_live"]
        plans = [
            {"periods": 3, "discount_pct": 10},
            {"periods": 6, "discount_pct": 15},
        ]
        resp = await client.patch(
            "/v1/merchants/me",
            json={"prepay_plans": plans},
            headers=auth_headers(key),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("prepay_plans") is not None
        assert len(data["prepay_plans"]) == 2
        assert data["prepay_plans"][0]["periods"] == 3
        assert data["prepay_plans"][0]["discount_pct"] == 10

    async def test_prepay_plans_validation(self, client, fresh_merchant):
        """Invalid prepay_plans rejected."""
        key = fresh_merchant["api_key_live"]
        # Duplicate periods
        resp = await client.patch(
            "/v1/merchants/me",
            json={"prepay_plans": [
                {"periods": 3, "discount_pct": 10},
                {"periods": 3, "discount_pct": 20},
            ]},
            headers=auth_headers(key),
        )
        assert resp.status_code == 400

    async def test_prepay_success(self, client, fresh_merchant):
        """Full prepay flow: configure plans, create subscription, prepay."""
        key = fresh_merchant["api_key_live"]

        # 1. Configure plans
        plans = [{"periods": 3, "discount_pct": 10}]
        resp = await client.patch(
            "/v1/merchants/me",
            json={"prepay_plans": plans},
            headers=auth_headers(key),
        )
        assert resp.status_code == 200

        # 2. Create customer + subscription (future start to avoid first invoice)
        cust = await _create_customer(client, key)
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        sub = await _create_subscription(
            client, key, cust["id"], amount="1.0", interval=30, start_at=future,
        )
        assert sub["status"] == "active"

        # 3. Prepay
        resp = await client.post(
            f"/v1/subscriptions/{sub['id']}/prepay",
            json={"periods": 3},
            headers=auth_headers(key),
        )
        assert resp.status_code == 201, f"Prepay failed: {resp.text}"
        data = resp.json()
        assert data["periods"] == 3
        assert data["discount_pct"] == 10
        assert data["invoice_id"] is not None
        assert data["prepaid_until"] is not None
        # 3 periods × 1.0 XMR × 0.9 = 2.7 XMR
        assert "2.7" in data["total_xmr"]

        # 4. Verify subscription has prepaid_until
        sub_resp = await client.get(
            f"/v1/subscriptions/{sub['id']}",
            headers=auth_headers(key),
        )
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["prepaid_until"] is not None

    async def test_prepay_cancelled_subscription(self, client, fresh_merchant):
        """Prepay fails on cancelled subscription."""
        key = fresh_merchant["api_key_live"]

        # Configure plans
        await client.patch(
            "/v1/merchants/me",
            json={"prepay_plans": [{"periods": 3, "discount_pct": 10}]},
            headers=auth_headers(key),
        )

        # Create + cancel subscription
        cust = await _create_customer(client, key)
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        sub = await _create_subscription(
            client, key, cust["id"], start_at=future,
        )
        await client.post(
            f"/v1/subscriptions/{sub['id']}/cancel",
            json={}, headers=auth_headers(key),
        )

        # Try prepay
        resp = await client.post(
            f"/v1/subscriptions/{sub['id']}/prepay",
            json={"periods": 3},
            headers=auth_headers(key),
        )
        assert resp.status_code == 409

    async def test_prepay_duplicate_blocked(self, client, fresh_merchant):
        """Second prepay blocked while first is pending."""
        key = fresh_merchant["api_key_live"]

        # Configure plans
        await client.patch(
            "/v1/merchants/me",
            json={"prepay_plans": [{"periods": 3, "discount_pct": 5}]},
            headers=auth_headers(key),
        )

        cust = await _create_customer(client, key)
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        sub = await _create_subscription(
            client, key, cust["id"], start_at=future,
        )

        # First prepay
        resp1 = await client.post(
            f"/v1/subscriptions/{sub['id']}/prepay",
            json={"periods": 3},
            headers=auth_headers(key),
        )
        assert resp1.status_code == 201

        # Second prepay — should be blocked
        resp2 = await client.post(
            f"/v1/subscriptions/{sub['id']}/prepay",
            json={"periods": 3},
            headers=auth_headers(key),
        )
        assert resp2.status_code == 409
        assert "pending" in resp2.json()["detail"].lower()

    async def test_prepay_wrong_periods(self, client, fresh_merchant):
        """Prepay with periods not in merchant plans."""
        key = fresh_merchant["api_key_live"]

        # Configure plans for 3 periods only
        await client.patch(
            "/v1/merchants/me",
            json={"prepay_plans": [{"periods": 3, "discount_pct": 10}]},
            headers=auth_headers(key),
        )

        cust = await _create_customer(client, key)
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        sub = await _create_subscription(
            client, key, cust["id"], start_at=future,
        )

        # Try prepay with 6 periods (not configured)
        resp = await client.post(
            f"/v1/subscriptions/{sub['id']}/prepay",
            json={"periods": 6},
            headers=auth_headers(key),
        )
        assert resp.status_code == 400
        assert "plan" in resp.json()["detail"].lower()
