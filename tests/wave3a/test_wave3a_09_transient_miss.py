from pathlib import Path


def test_unconfirmed_checker_requires_three_consecutive_misses():
    source = Path("backend/app/tasks/detection_confirmations.py").read_text()
    assert "TX_MISS_ORPHAN_THRESHOLD: int = 3" in source
    assert "_tx_miss_counts" in source
    assert "miss_count < TX_MISS_ORPHAN_THRESHOLD" in source
    assert "not orphaning yet" in source
