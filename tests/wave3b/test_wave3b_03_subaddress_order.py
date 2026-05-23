from pathlib import Path

SOURCE = Path("backend/app/services/invoice_service.py")


def test_invoice_flushes_before_wallet_subaddress_allocation_and_cleans_up():
    source = SOURCE.read_text()
    create_start = source.index("async def create_invoice")
    create_body = source[create_start : source.index("async def get_invoice")]
    assert "db.add(invoice)\n        await db.flush()" in create_body
    assert create_body.index("await db.flush()") < create_body.index("addr_result = await rpc.create_address")
    assert "await db.delete(invoice)" in create_body
    assert "address_index: int = addr_result" in create_body
