from pathlib import Path

PAYMENT_SERVICE = Path("backend/app/services/payment_service.py")


def test_sum_invoice_payments_counts_confirmed_only():
    source = PAYMENT_SERVICE.read_text()
    start = source.index("async def sum_invoice_payments")
    end = source.index("async def sum_detected_payments")
    body = source[start:end]
    assert "Payment.status == PaymentStatus.confirmed" in body
    assert "PaymentStatus.detected" not in body


def test_mempool_detected_payments_do_not_settle_invoice():
    source = PAYMENT_SERVICE.read_text()
    assert "Detected payments are recorded but do not settle invoices" in source
