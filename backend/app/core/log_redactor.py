"""Log redaction filter.

Attached to root and uvicorn handlers so child loggers cannot bypass redaction.
Strips: API keys, view keys, tx hashes, Monero addresses, hex secrets.

CRITICAL: IP addresses are never logged in the first place (by design).
This filter is a safety net for anything that slips through.

Usage (in main.py startup):
    from app.core.log_redactor import setup_log_redaction
    setup_log_redaction()
"""

import logging
import re
from typing import Pattern

# Compiled redaction patterns (order matters — most specific first)
REDACTION_RULES: list[tuple[Pattern[str], str]] = [
    # GhostBill API keys: gb_live_<32hex> or gb_test_<32hex>
    (
        re.compile(r"gb_(live|test)_[a-fA-F0-9]{32}"),
        "[REDACTED_APIKEY]",
    ),
    # Monero primary address (starts with 4, 95 chars base58)
    (
        re.compile(r"4[1-9A-HJ-NP-Za-km-z]{94}"),
        "[REDACTED_ADDRESS]",
    ),
    # Monero subaddress (starts with 8, 95 chars base58)
    (
        re.compile(r"8[1-9A-HJ-NP-Za-km-z]{94}"),
        "[REDACTED_SUBADDRESS]",
    ),
    # View keys, tx hashes, secret keys (exactly 64 hex chars)
    (
        re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])"),
        "[REDACTED_HEX64]",
    ),
    # Generic long hex strings (32+ chars, catch-all for other secrets)
    (
        re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{32,}(?![a-fA-F0-9])"),
        "[REDACTED_HEX]",
    ),
    # Bearer tokens in log output
    (
        re.compile(r"Bearer\s+\S+"),
        "Bearer [REDACTED]",
    ),
    # Base64 blobs that might be encrypted view keys (40+ chars)
    (
        re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])"),
        "[REDACTED_B64]",
    ),
]


def redact(message: str) -> str:
    """Apply all redaction rules to a log message."""
    for pattern, replacement in REDACTION_RULES:
        message = pattern.sub(replacement, message)
    return message


class RedactionFilter(logging.Filter):
    """Logging filter that redacts sensitive data from log records.

    Applied to all log output. Modifies the record in-place before
    it reaches any handler (stdout, file, etc.).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the main message
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)

        # Redact args if they contain strings
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact(str(a)) if isinstance(a, str) else a for a in record.args)

        # Redact exception text if present
        if record.exc_text and isinstance(record.exc_text, str):
            record.exc_text = redact(record.exc_text)

        return True  # Always pass through (we modify, not filter)


def setup_log_redaction() -> None:
    """Attach redaction filter to root and uvicorn handlers.

    Call once during app startup (before any request processing).
    Safe to call multiple times (checks for existing filter).
    """
    redaction_filter = RedactionFilter()
    for logger_name in ("", "uvicorn.error", "uvicorn.access"):
        target_logger = logging.getLogger(logger_name)
        for handler in target_logger.handlers:
            if not any(isinstance(existing_filter, RedactionFilter) for existing_filter in handler.filters):
                handler.addFilter(redaction_filter)
    logging.getLogger(__name__).info("Log redaction filter activated")
