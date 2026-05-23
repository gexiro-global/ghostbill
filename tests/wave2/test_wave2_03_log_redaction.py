import io
import logging

from app.core.log_redactor import setup_log_redaction


def test_child_logger_output_is_redacted():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.handlers = [handler]
    setup_log_redaction()

    logging.getLogger("app.child").warning("key=gb_live_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert "[REDACTED_APIKEY]" in stream.getvalue()
    assert "gb_live_" not in stream.getvalue()
