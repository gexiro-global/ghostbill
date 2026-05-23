from pathlib import Path


def test_redundant_exception_tuple_removed():
    source = (Path("backend/app/main.py")).read_text()
    assert "except (WalletUnavailableError, Exception)" not in source
    assert "except Exception as exc" in source
