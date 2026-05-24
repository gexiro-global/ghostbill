import pytest

from app.config import settings

from .conftest import auth_headers, internal_headers

pytestmark = pytest.mark.integration


async def test_internal_renewal_requires_secret(client):
    resp = await client.post("/v1/internal/trigger-renewal")
    assert resp.status_code in (401, 403, 503)


async def test_internal_renewal_with_secret(client):
    if not settings.internal_secret:
        pytest.skip("INTERNAL_SECRET is not configured in this environment")
    resp = await client.post("/v1/internal/trigger-renewal", headers=internal_headers())
    assert resp.status_code in (200, 202)


async def test_internal_renewal_wrong_secret(client):
    resp = await client.post("/v1/internal/trigger-renewal", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code in (401, 403)


async def test_admin_renewal_requires_admin(client, service_merchant):
    resp = await client.post("/v1/admin/trigger-renewal", headers=auth_headers(service_merchant["api_key"]))
    assert resp.status_code in (401, 403)
