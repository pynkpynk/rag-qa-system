from __future__ import annotations

import logging
import os
import re

_REPLACEMENTS = [
    (re.compile(r"sk-[A-Za-z0-9-]{10,}"), "sk-REDACTED"),
    (re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"), "sk-proj-REDACTED"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+"), "Bearer REDACTED"),
]

_PATCHED = False


def _apply_redaction(text: str) -> str:
    sanitized = text
    for pattern, repl in _REPLACEMENTS:
        sanitized = pattern.sub(repl, sanitized)
    return sanitized


def install_log_redaction_filter() -> None:
    global _PATCHED
    if _PATCHED or os.getenv("DISABLE_LOG_REDACTION", "0") == "1":
        return
    original_get_message = logging.LogRecord.getMessage

    def redacted_get_message(self: logging.LogRecord) -> str:  # type: ignore[override]
        message = original_get_message(self)
        return _apply_redaction(message)

    logging.LogRecord.getMessage = redacted_get_message  # type: ignore[assignment]
    _PATCHED = True


def install_redaction_filter() -> None:
    install_log_redaction_filter()
