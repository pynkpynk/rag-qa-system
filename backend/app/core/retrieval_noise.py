from __future__ import annotations

import re
from typing import Any, Iterable


_NOISE_PHRASES = (
    "list of figures",
    "list of tables",
    "table of contents",
    "glossary",
    "index",
    "appendix",
    "目次",
    "図表",
    "索引",
)
_FRONT_MATTER_PHRASES = (
    "acknowledgments",
    "acknowledgements",
    "this publication is available free of charge",
    "national institute of standards and technology",
    "nist cswp",
    "doi.org/",
    "digitaldoi",
    "preface",
    "executive summary",
)

_QUESTION_BYPASS_PHRASES = (
    "table of contents",
    "list of figures",
    "list of tables",
    "glossary",
    "index",
    "目次",
    "図",
    "図表",
    "索引",
)
_DOT_LEADER_RE = re.compile(r"\.{5,}")
_ROMAN_NUMERAL_RE = re.compile(r"\b[ivxlcdm]{1,4}\b", re.IGNORECASE)


def is_noise_text(text: str) -> bool:
    if not text:
        return False
    normalized = text.lower()
    if any(phrase in normalized for phrase in _NOISE_PHRASES):
        return True
    if any(phrase in normalized for phrase in _FRONT_MATTER_PHRASES):
        return True
    if "doi.org" in normalized:
        return True
    if "national institute of standards and technology" in normalized:
        return True
    if _DOT_LEADER_RE.search(text):
        lines = text.splitlines()
        leader_lines = sum(1 for line in lines if _DOT_LEADER_RE.search(line))
        if leader_lines >= 2:
            return True
        dot_total = text.count(".")
        if dot_total >= 40 and dot_total / max(len(text), 1) > 0.2:
            return True
    if _ROMAN_NUMERAL_RE.search(text) and "acknowled" in normalized:
        return True
    return False


def should_bypass_noise_filter(question: str) -> bool:
    if not question:
        return False
    normalized = question.lower()
    return any(phrase in normalized for phrase in _QUESTION_BYPASS_PHRASES)


def _extract_text(candidate: Any) -> str:
    if isinstance(candidate, dict):
        value = candidate.get("text")
    else:
        value = getattr(candidate, "text", None)
    if value is None:
        return ""
    return str(value)


def filter_noise_candidates(
    candidates: Iterable[Any], question: str, keep: int
) -> list[Any]:
    keep_count = max(int(keep or 0), 0)
    if keep_count == 0:
        return []
    candidate_list = list(candidates)
    if not candidate_list:
        return []
    if should_bypass_noise_filter(question):
        return candidate_list[:keep_count]
    good: list[Any] = []
    noise: list[Any] = []
    for cand in candidate_list:
        text = _extract_text(cand)
        if text and is_noise_text(text):
            noise.append(cand)
        else:
            good.append(cand)
        if len(good) >= keep_count:
            return good[:keep_count]

    result = list(good)
    if len(result) < keep_count:
        needed = keep_count - len(result)
        result.extend(noise[:needed])
    return result
