from __future__ import annotations

import os
from pathlib import Path
from typing import Final


_GIT_ENV_VARS: Final[tuple[str, ...]] = (
    "GIT_SHA",
    "RENDER_GIT_COMMIT",
    "VERCEL_GIT_COMMIT_SHA",
    "GITHUB_SHA",
    "BUILD_ID",
)

_EMBEDDED_SHA_PATH = Path(__file__).resolve().parents[1] / "_build" / "git_sha.txt"


def _read_embedded_git_sha() -> str | None:
    try:
        if _EMBEDDED_SHA_PATH.is_file():
            content = _EMBEDDED_SHA_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
    except OSError:
        pass
    return None


def get_git_sha() -> str:
    for var in _GIT_ENV_VARS:
        value = os.getenv(var)
        if value:
            return value
    embedded = _read_embedded_git_sha()
    if embedded:
        return embedded
    return "unknown"
