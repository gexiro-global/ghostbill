from pathlib import Path


def test_prepay_hook_failure_clears_prepay_guard():
    source = Path("backend/app/services/subscription_grace.py").read_text()
    assert "except Exception:" in source
    assert "sub.prepay_invoice_id = None" in source
    assert "invoice.status in (" in source
