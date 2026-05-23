from pathlib import Path

SOURCE = Path("backend/app/services/subscription_service.py")


def test_cancel_subscription_logs_invoice_cancel_failure_as_error_with_metadata():
    source = SOURCE.read_text()
    cancel_start = source.index("async def cancel_subscription")
    helper_start = source.index("# ── Helpers")
    cancel_body = source[cancel_start:helper_start]
    assert "logger.error(" in cancel_body
    assert "Failed to cancel invoice %s during subscription cancellation" in cancel_body
    assert '"invoice_cancellation_failed": invoice_cancellation_failed' in cancel_body
    assert '"invoice_id": failed_invoice_id' in cancel_body
    assert '"warning": "invoice_cancellation_failed"' in cancel_body
    assert '"subscription.cancelled"' in cancel_body
