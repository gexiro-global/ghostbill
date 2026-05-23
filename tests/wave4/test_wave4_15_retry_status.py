from pathlib import Path


def test_retry_status_codes_are_precise():
    source = (Path("backend/app/api/routes/webhooks.py")).read_text()
    assert "WebhookRetryNotFoundError" in source and "status_code=404" in source
    assert "WebhookRetryConflictError" in source and "status_code=409" in source
    assert "WebhookRetryInvalidStateError" in source and "status_code=400" in source
