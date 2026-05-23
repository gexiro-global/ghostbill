from pathlib import Path


def test_prepay_fulfillment_checks_existing_invoice_rows():
    source = Path("backend/app/services/subscription_prepay.py").read_text()
    assert "existing_stmt = select(func.count(SubscriptionPayment.id))" in source
    assert "SubscriptionPayment.invoice_id == invoice.id" in source
    assert "already fulfilled" in source
    assert "return" in source[source.index("existing_count") : source.index("# Create N subscription_payment records")]
