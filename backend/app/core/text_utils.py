from __future__ import annotations

import re

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def strip_control_chars(text: str | None) -> str:
    if not isinstance(text, str):
        return "" if text is None else str(text)
    return _CONTROL_CHARS_RE.sub(" ", text)
