from pathlib import Path

SOURCE = Path("backend/app/api/routes/public_invoice.py")


def test_public_invoice_strips_description_and_fiat_by_default():
    source = SOURCE.read_text()
    fetch_start = source.index("async def _fetch_invoice_public_data")
    public_start = source.index("# ── Public Invoice Data")
    fetch_body = source[fetch_start:public_start]
    base_payload = fetch_body[fetch_body.index("data = {") : fetch_body.index("if metadata.get")]
    assert '"fiat_amount"' not in base_payload
    assert '"fiat_currency"' not in base_payload
    assert '"description"' not in base_payload
    assert 'metadata.get("show_description") is True' in fetch_body
    assert 'data["description"] = invoice.description' in fetch_body
