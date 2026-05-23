from pathlib import Path


def test_confirmation_task_uses_payment_service_update_path():
    source = Path("backend/app/tasks/detection_confirmations.py").read_text()
    assert "payment_service._update_confirmations" in source
    assert "payment.status = PaymentStatus.confirmed" not in source
    assert "payment.confirmed_at =" not in source
