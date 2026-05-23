from pathlib import Path


def test_queue_webhook_validates_event_registry():
    source = (Path("backend/app/services/webhook_service.py")).read_text()
    assert "VALID_EVENTS" in source
    assert "if event_type not in VALID_EVENTS" in source
    assert "raise ValueError" in source
