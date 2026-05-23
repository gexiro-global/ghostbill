import pathlib


def test_internal_exception_response_is_generic():
    source = pathlib.Path("app/main.py").read_text()
    assert '"Internal error processing request"' in source
    assert '"error": str(exc)' not in source
