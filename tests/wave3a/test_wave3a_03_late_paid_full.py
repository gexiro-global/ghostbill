from pathlib import Path


def test_expired_invoice_requires_full_confirmed_amount_for_late_paid():
    source = Path("backend/app/services/payment_service.py").read_text()
    expired_block = source[
        source.index("if invoice.status == InvoiceStatus.expired") : source.index(
            "elif invoice.status == InvoiceStatus.late_paid"
        )
    ]
    assert "if cumulative >= required" in expired_block
    assert "new_status = InvoiceStatus.late_paid" in expired_block
    assert "new_status = InvoiceStatus.expired" in expired_block
