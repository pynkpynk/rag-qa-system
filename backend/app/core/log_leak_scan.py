from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Union
from os import PathLike

@dataclass
class Violation:
    pattern_name: str
    snippet: str
    line_no: int

    @property
    def name(self) -> str:
        """
        Backward-compatible alias for the rule identifier.
        """
        return self.pattern_name

JWT_LIKE_RE = re.compile(
    r"""
    \b                      # word boundary
    eyJ[A-Za-z0-9_-]{10,}   # header (base64url, typically starts with eyJ)
    \.                      # separator
    [A-Za-z0-9_-]{10,}      # payload segment
    (?:\.[A-Za-z0-9_-]{10,})?  # optional signature
    (?=[\s\)\}\],;:\"']|$)  # must end before whitespace/punct/eol
    """,
    re.VERBOSE,
)

FORBIDDEN_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    ("bearer_header", re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE)),
    ("sk_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("private_key_block", re.compile(r"BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY")),
    ("aws_secret", re.compile(r"AWS_(?:SECRET|ACCESS)_KEY[_A-Z]*\s*=\s*\S+", re.IGNORECASE)),
    ("jwt_blob", JWT_LIKE_RE),
    ("token_keyword", re.compile(r"(api[_-]?key|secret|token)\s*[:=]\s*\S+", re.IGNORECASE)),
]

REDACT_PREFIX = 8
REDACT_SUFFIX = 4


def _redact(value: str) -> str:
    if len(value) <= REDACT_PREFIX + REDACT_SUFFIX:
        return value[:4] + "…"
    return value[:REDACT_PREFIX] + "…" + value[-REDACT_SUFFIX:]


def scan_lines(lines: Iterable[str]) -> list[Violation]:
    violations: list[Violation] = []
    for idx, line in enumerate(lines, start=1):
        for name, pattern in FORBIDDEN_REGEXES:
            for match in pattern.finditer(line):
                snippet = _redact(match.group(0))
                violations.append(Violation(name, snippet, idx))
    return violations


def scan_text(text: str) -> list[Violation]:
    return scan_lines(text.splitlines())


PathInput = Union[str, PathLike[str], Path]


def scan_file(path: PathInput) -> list[Violation]:
    file_path = Path(path)
    content = file_path.read_text(errors="ignore") if file_path.exists() else ""
    return scan_text(content)


def format_report(violations: list[Violation]) -> str:
    if not violations:
        return ""
    lines = ["Forbidden patterns detected in test logs:"]
    for v in violations:
        lines.append(f"- pattern={v.pattern_name} line={v.line_no} snippet={v.snippet}")
    return "\n".join(lines)
