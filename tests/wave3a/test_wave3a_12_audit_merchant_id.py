from pathlib import Path


def test_payment_confirmed_and_orphaned_audits_use_invoice_merchant_id():
    source = Path("backend/app/services/payment_service.py").read_text()
    assert 'action="payment.confirmed"' in source
    assert 'action="payment.orphaned"' in source
    assert "merchant_id=invoice.merchant_id if invoice is not None else None" in source
    assert "merchant_id=None,  # Will be set if needed" not in source
