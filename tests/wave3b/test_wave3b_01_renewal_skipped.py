from pathlib import Path

SOURCE = Path("backend/app/services/subscription_renewal.py")


def test_renewal_logs_skipped_periods_metadata():
    source = SOURCE.read_text()
    assert "def calculate_skipped_periods" in source
    assert '"skipped_periods": skipped_periods' in source
    assert "logger.warning(" in source
    assert "Renewal skipped %d billable periods" in source
