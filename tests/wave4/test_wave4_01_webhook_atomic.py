from pathlib import Path

# PATCH removed


def test_webhook_claim_uses_skip_locked():
    service = (Path("backend/app/services/webhook_service.py")).read_text()
    worker = (Path("backend/app/tasks/webhook_worker.py")).read_text()
    assert "with_for_update(skip_locked=True)" in service
    assert "claim_pending_deliveries" in worker
