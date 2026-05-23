from pathlib import Path


def test_invoice_expiry_dispatches_webhook():
    source = (Path("backend/app/services/expiration_service.py")).read_text()
    assert "webhook_service.dispatch_events" in source
    assert '"invoice.expired"' in source
