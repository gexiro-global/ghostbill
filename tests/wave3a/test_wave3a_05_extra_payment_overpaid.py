from pathlib import Path


def test_process_transfer_does_not_skip_paid_or_overpaid_invoices():
    source = Path("backend/app/services/payment_service.py").read_text()
    process_transfer = source[source.index("async def process_transfer") : source.index("async def _create_payment")]
    assert "TERMINAL_STATUSES" not in process_transfer
    assert "invoice.status != InvoiceStatus.cancelled" in process_transfer


def test_paid_invoice_can_transition_to_overpaid():
    source = Path("backend/app/services/invoice_service.py").read_text()
    paid_block = source[source.index("InvoiceStatus.paid: [") : source.index("InvoiceStatus.overpaid: [")]
    assert "InvoiceStatus.overpaid" in paid_block
