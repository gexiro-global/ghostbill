from pathlib import Path


def test_cancelled_invoice_payment_records_exception_and_skips_recalc():
    source = Path("backend/app/services/payment_service.py").read_text()
    assert '"cancelled_invoice_payment"' in source
    assert "if invoice.status != InvoiceStatus.cancelled:" in source
    assert '"invoice.exception_payment"' in source


def test_cancelled_is_only_terminal_status():
    source = Path("backend/app/services/invoice_service.py").read_text()
    terminal = source[source.index("TERMINAL_STATUSES") : source.index("class InvoiceError")]
    assert "InvoiceStatus.cancelled" in terminal
    assert "InvoiceStatus.paid" not in terminal
    assert "InvoiceStatus.overpaid" not in terminal
    assert "InvoiceStatus.late_paid" not in terminal
