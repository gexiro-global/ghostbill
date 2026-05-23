from pathlib import Path

SOURCE = Path("backend/app/services/analytics_service.py")


def test_revenue_splits_gross_received_from_invoice_revenue():
    source = SOURCE.read_text()
    revenue_start = source.index("async def get_revenue")
    stats_start = source.index("# Invoice stats")
    revenue_body = source[revenue_start:stats_start]
    assert "gross_received_atomic" in revenue_body
    assert "invoice_revenue_atomic" in revenue_body
    assert "min(gross_received_atomic, int(row.invoice_amount_atomic or 0))" in revenue_body
    assert '"gross_received_xmr"' in revenue_body
    assert '"invoice_revenue_xmr"' in revenue_body
