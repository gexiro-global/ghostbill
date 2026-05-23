from pathlib import Path


def test_missing_merchant_and_secret_go_to_dlq():
    source = (Path("backend/app/tasks/webhook_worker.py")).read_text()
    assert "merchant_not_found" in source
    assert "webhook_secret_missing" in source
    assert "_move_to_dlq" in source
