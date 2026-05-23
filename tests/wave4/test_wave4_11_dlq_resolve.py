from pathlib import Path


def test_dlq_retry_resolution_is_idempotent():
    service = (Path("backend/app/services/webhook_service.py")).read_text()
    routes = (Path("backend/app/api/routes/webhooks.py")).read_text()
    assert "if dlq_entry.resolved" in service
    assert "resolved_delivery_id" in service
    assert "WebhookDeadLetter.resolved.is_(False)" in routes
    assert "status_code=409" in routes
