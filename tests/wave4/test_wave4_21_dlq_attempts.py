from pathlib import Path


def test_dlq_details_include_attempt_counts():
    source = (Path("backend/app/services/webhook_service.py")).read_text()
    assert '"attempt_count": delivery.attempts' in source
    assert '"max_attempts": delivery.max_attempts' in source
