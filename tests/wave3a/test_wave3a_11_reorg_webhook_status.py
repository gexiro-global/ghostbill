from pathlib import Path


def test_reorg_webhook_captures_old_invoice_status_before_handle_reorg():
    source = Path("backend/app/tasks/detection_confirmations.py").read_text()
    before = source.index("old_invoice_status = invoice_before.status")
    reorg = source.index("await payment_service.handle_reorg")
    determine = source.index("payment_service.determine_webhook_events", reorg)
    assert before < reorg < determine
    assert "old_invoice_status=old_invoice_status or invoice.status" in source


def test_invoice_reverted_event_registered():
    source = Path("backend/app/services/payment_service.py").read_text()
    assert '"invoice.reverted"' in source
