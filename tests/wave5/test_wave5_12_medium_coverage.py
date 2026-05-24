import pytest

from app.services.invoice_service import WalletUnavailableError, invoice_service
from app.services.monero_rpc import MoneroRPCConnectionError

from .conftest import auth_headers, create_test_invoice, create_test_subscription

pytestmark = pytest.mark.integration


async def test_sse_endpoint_streams(client, db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    async with client.stream("GET", f"/v1/invoices/{invoice.id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")


async def test_invoice_creation_wallet_failure(monkeypatch, db_session, service_merchant):
    class FailingRPC:
        async def create_address(self, account_index=0, label=None):
            raise MoneroRPCConnectionError("wallet unavailable")

    monkeypatch.setattr("app.services.invoice_service.get_monero_rpc", lambda: FailingRPC())
    merchant = service_merchant["merchant"]
    with pytest.raises(WalletUnavailableError):
        await invoice_service.create_invoice(db_session, merchant, "1", expires_in=600)


async def test_cursor_pagination_returns_correct_page(client, db_session, service_merchant):
    await create_test_invoice(db_session, service_merchant["merchant_id"])
    await create_test_invoice(db_session, service_merchant["merchant_id"])
    await create_test_invoice(db_session, service_merchant["merchant_id"])

    resp = await client.get("/v1/invoices?limit=1", headers=auth_headers(service_merchant["api_key"]))
    assert resp.status_code == 200
    page = resp.json()
    assert len(page["data"]) == 1

    cursor = page["data"][0]["id"]
    resp2 = await client.get(
        f"/v1/invoices?limit=10&starting_after={cursor}",
        headers=auth_headers(service_merchant["api_key"]),
    )
    assert resp2.status_code == 200
    ids2 = [row["id"] for row in resp2.json()["data"]]
    assert cursor not in ids2


async def test_invalid_amount_rejected(client, service_merchant):
    for amount in ("0", "-1"):
        resp = await client.post(
            "/v1/invoices",
            json={"amount_xmr": amount, "expires_in": 600},
            headers=auth_headers(service_merchant["api_key"]),
        )
        assert resp.status_code in (400, 422)


async def test_invalid_interval_rejected(client, db_session, service_merchant):
    customer, _ = await create_test_subscription(db_session, service_merchant["merchant_id"])
    payload = {"customer_id": str(customer.id), "amount_xmr": "1", "interval_days": 0}
    resp = await client.post("/v1/subscriptions", json=payload, headers=auth_headers(service_merchant["api_key"]))
    assert resp.status_code in (400, 422)


async def test_list_endpoint_shows_created(client, db_session, service_merchant):
    invoice = await create_test_invoice(db_session, service_merchant["merchant_id"])
    resp = await client.get("/v1/invoices", headers=auth_headers(service_merchant["api_key"]))
    assert resp.status_code == 200
    assert str(invoice.id) in {row["id"] for row in resp.json()["data"]}


async def test_admin_key_empty_rejected(client):
    resp = await client.get("/v1/admin/stats")
    assert resp.status_code in (401, 403)
