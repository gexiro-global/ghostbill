from pathlib import Path


def test_retention_deletes_children_before_parents():
    source = (Path("backend/app/tasks/data_retention.py")).read_text()
    assert source.index("DELETE FROM invoice_addresses") < source.index("DELETE FROM invoices")
    assert source.index("DELETE FROM webhook_dead_letters") < source.index("DELETE FROM webhook_deliveries")
