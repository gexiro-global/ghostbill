from pathlib import Path

PAYMENT_SERVICE = Path("backend/app/services/payment_service.py")
INVOICE_SERVICE = Path("backend/app/services/invoice_service.py")


def test_paid_statuses_are_not_terminal_for_reorg():
    source = PAYMENT_SERVICE.read_text()
    recalc = source[
        source.index("async def _recalculate_invoice_status") : source.index("async def sum_invoice_payments")
    ]
    assert "invoice.status == InvoiceStatus.cancelled" in recalc
    # Verify no early-return for paid/overpaid/late_paid (the old pattern was:
    #   if invoice.status in (InvoiceStatus.paid, ...): return invoice.status)
    assert "return invoice.status" not in recalc.split("# Cancelled invoices")[0].split("cumulative = ")[0]


def test_reorg_reverse_transitions_are_allowed():
    source = INVOICE_SERVICE.read_text()
    assert "InvoiceStatus.paid: [" in source
    assert "InvoiceStatus.partially_paid" in source
    assert "InvoiceStatus.pending" in source
    assert "InvoiceStatus.late_paid: [\n        InvoiceStatus.expired" in source
