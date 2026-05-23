from pathlib import Path


def test_hmac_signs_timestamp_and_delivery_id():
    source = (Path("backend/app/services/webhook_service.py")).read_text()
    assert "X-GhostBill-Timestamp" in source
    assert "X-GhostBill-Delivery-Id" in source
    assert "timestamp=timestamp, delivery_id=delivery_id" in source
