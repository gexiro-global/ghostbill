from pathlib import Path

SOURCE = Path("backend/app/api/routes/public_invoice.py")


def test_pay_page_checks_invoice_exists_before_rendering():
    source = SOURCE.read_text()
    serve_start = source.index("async def serve_payment_page")
    serve_body = source[serve_start:]
    assert "select(Invoice.id).where(Invoice.id == parsed_id)" in serve_body
    assert "status_code=status.HTTP_404_NOT_FOUND" in serve_body
    assert "Payment page not available" in serve_body
