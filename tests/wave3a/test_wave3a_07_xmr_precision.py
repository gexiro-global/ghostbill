from pathlib import Path


def test_invoice_creation_rejects_zero_atomic_positive_amounts():
    source = Path("backend/app/services/invoice_service.py").read_text()
    assert "amount_atomic = xmr_to_atomic(amount_xmr)" in source
    assert "if amount_atomic <= 0:" in source
    assert "below the minimum atomic unit" in source
