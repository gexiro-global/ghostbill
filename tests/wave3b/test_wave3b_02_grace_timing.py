from pathlib import Path

SOURCE = Path("backend/app/services/subscription_grace.py")


def test_hard_grace_requires_invoice_to_be_expired():
    source = SOURCE.read_text()
    hard_start = source.index("# Hard grace")
    recovery_start = source.index("# Recovery")
    hard_section = source[hard_start:recovery_start]
    assert "Invoice.expires_at <= now" in hard_section
    assert "InvoiceStatus.pending" in hard_section
    assert "InvoiceStatus.partially_paid" in hard_section
