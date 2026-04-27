"""License system tests.

Covers:
    - POST /v1/admin/licenses (create)
    - GET /v1/admin/licenses (list)
    - DELETE /v1/admin/licenses/{id} (deactivate)
    - GET /v1/license/verify (public verify)
    - Edge cases: invalid tier, expired, deactivated, invalid key

Requires:
    GHOSTBILL_ADMIN_KEY  — admin API key
    GHOSTBILL_TEST_DB    — PostgreSQL DSN
"""

import os
import uuid

import pytest

from tests.conftest import auth_headers, db_execute

ADMIN_KEY = os.getenv("GHOSTBILL_ADMIN_KEY", "")


# ── Cleanup helper ───────────────────────────────────────────────────────


async def _cleanup_test_licenses():
    """Remove test licenses created during tests."""
    await db_execute("DELETE FROM licenses WHERE email LIKE '%@test-license.local'")


# ── Create License ──────────────────────────────────────────────────────


class TestCreateLicense:
    @pytest.mark.asyncio
    async def test_create_starter(self, client):
        """Create a starter license — returns plaintext key."""
        await _cleanup_test_licenses()
        resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "starter", "email": "create@test-license.local", "duration_days": 30},
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "key" in data
        assert data["key"].startswith("gbl_starter_")
        assert len(data["key"]) == len("gbl_starter_") + 32
        lic = data["license"]
        assert lic["tier"] == "starter"
        assert lic["active"] is True
        assert lic["email"] == "create@test-license.local"
        assert lic["expires_at"] is not None
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_create_growth_no_expiry(self, client):
        """Create a growth license without expiry."""
        await _cleanup_test_licenses()
        resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "growth", "email": "growth@test-license.local"},
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"].startswith("gbl_growth_")
        assert data["license"]["expires_at"] is None
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_create_invalid_tier(self, client):
        """Invalid tier returns 400."""
        resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "premium", "email": "bad@test-license.local"},
            headers=auth_headers(ADMIN_KEY),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_no_auth(self, client):
        """Create without auth returns 401."""
        resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "starter", "email": "noauth@test-license.local"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_non_admin(self, client, fresh_merchant):
        """Non-admin merchant returns 403."""
        resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "starter", "email": "nonadmin@test-license.local"},
            headers=auth_headers(fresh_merchant["api_key_live"]),
        )
        assert resp.status_code == 403


# ── List Licenses ───────────────────────────────────────────────────────


class TestListLicenses:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        """List returns array (may be empty)."""
        await _cleanup_test_licenses()
        resp = await client.get("/v1/admin/licenses", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        data = resp.json()
        assert "licenses" in data
        assert isinstance(data["licenses"], list)

    @pytest.mark.asyncio
    async def test_list_with_data(self, client):
        """Create one, then list — should include it."""
        await _cleanup_test_licenses()
        # Create
        create_resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "enterprise", "email": "list@test-license.local"},
            headers=auth_headers(ADMIN_KEY),
        )
        assert create_resp.status_code == 201

        # List
        resp = await client.get("/v1/admin/licenses", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        licenses = resp.json()["licenses"]
        found = [lic for lic in licenses if lic["email"] == "list@test-license.local"]
        assert len(found) == 1
        assert found[0]["tier"] == "enterprise"
        await _cleanup_test_licenses()


# ── Deactivate License ─────────────────────────────────────────────────


class TestDeactivateLicense:
    @pytest.mark.asyncio
    async def test_deactivate(self, client):
        """Deactivate sets active=false."""
        await _cleanup_test_licenses()
        # Create
        create_resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "starter", "email": "deactivate@test-license.local", "duration_days": 365},
            headers=auth_headers(ADMIN_KEY),
        )
        assert create_resp.status_code == 201
        license_id = create_resp.json()["license"]["id"]

        # Deactivate
        resp = await client.delete(f"/v1/admin/licenses/{license_id}", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 200
        assert resp.json()["deactivated"] is True
        assert resp.json()["license"]["active"] is False
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_deactivate_not_found(self, client):
        """Deactivate non-existent license returns 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/v1/admin/licenses/{fake_id}", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_invalid_id(self, client):
        """Deactivate with invalid UUID returns 404."""
        resp = await client.delete("/v1/admin/licenses/not-a-uuid", headers=auth_headers(ADMIN_KEY))
        assert resp.status_code == 404


# ── Verify License ──────────────────────────────────────────────────────


class TestVerifyLicense:
    @pytest.mark.asyncio
    async def test_verify_valid(self, client):
        """Verify a valid license returns tier + limits."""
        await _cleanup_test_licenses()
        # Create
        create_resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "growth", "email": "verify@test-license.local", "duration_days": 365},
            headers=auth_headers(ADMIN_KEY),
        )
        assert create_resp.status_code == 201
        key = create_resp.json()["key"]

        # Verify (public, no auth)
        resp = await client.get("/v1/license/verify", params={"key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["tier"] == "growth"
        assert data["limits"]["analytics"] is True
        assert data["limits"]["admin"] is True
        assert data["limits"]["invoices_per_month"] == -1
        assert data["expires_at"] is not None
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_verify_community(self, client):
        """Community tier returns correct limits."""
        await _cleanup_test_licenses()
        create_resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "community", "email": "community@test-license.local"},
            headers=auth_headers(ADMIN_KEY),
        )
        assert create_resp.status_code == 201
        key = create_resp.json()["key"]

        resp = await client.get("/v1/license/verify", params={"key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["tier"] == "community"
        assert data["limits"]["analytics"] is False
        assert data["limits"]["admin"] is False
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_verify_invalid_key(self, client):
        """Invalid key returns valid=false."""
        resp = await client.get("/v1/license/verify", params={"key": "gbl_starter_" + "x" * 32})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_verify_deactivated(self, client):
        """Deactivated license returns valid=false."""
        await _cleanup_test_licenses()
        # Create
        create_resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "starter", "email": "deact-verify@test-license.local", "duration_days": 365},
            headers=auth_headers(ADMIN_KEY),
        )
        assert create_resp.status_code == 201
        key = create_resp.json()["key"]
        license_id = create_resp.json()["license"]["id"]

        # Deactivate
        await client.delete(f"/v1/admin/licenses/{license_id}", headers=auth_headers(ADMIN_KEY))

        # Verify should fail
        resp = await client.get("/v1/license/verify", params={"key": key})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_verify_expired(self, client):
        """Expired license returns valid=false."""
        await _cleanup_test_licenses()
        # Create with 1 day duration
        create_resp = await client.post(
            "/v1/admin/licenses",
            json={"tier": "starter", "email": "expired@test-license.local", "duration_days": 1},
            headers=auth_headers(ADMIN_KEY),
        )
        assert create_resp.status_code == 201
        key = create_resp.json()["key"]

        # Force expire in DB
        await db_execute(
            "UPDATE licenses SET expires_at = NOW() - interval '1 day' WHERE email = 'expired@test-license.local'"
        )

        # Verify should fail
        resp = await client.get("/v1/license/verify", params={"key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        await _cleanup_test_licenses()

    @pytest.mark.asyncio
    async def test_verify_missing_key_param(self, client):
        """Missing key param returns 422."""
        resp = await client.get("/v1/license/verify")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_short_key(self, client):
        """Too-short key returns 422 (min_length=10)."""
        resp = await client.get("/v1/license/verify", params={"key": "gbl_x"})
        assert resp.status_code == 422
