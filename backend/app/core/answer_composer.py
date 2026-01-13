from __future__ import annotations

import re
from typing import Any, Iterable, Sequence


_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_EN_DOC_REF_RE = re.compile(r"\[S\d+[^\]]*\]")
_PAGE_REF_RE = re.compile(r"\bp\.\s*\d+\b", re.IGNORECASE)
_SENTENCE_RE_EN = re.compile(r"[^.!?]+(?:[.!?])?")
_SENTENCE_RE_JA = re.compile(r"[^。！？]+(?:[。！？])?")
_URL_RE = re.compile(r"https?://\S+|doi:\S+", re.IGNORECASE)
_HEADER_RE = re.compile(r"^(list of|table of|figure|fig\.|chapter)\b", re.IGNORECASE)

MappingLike = Any


def detect_language(text: str) -> str:
    if not text:
        return "en"
    cjk = len(_CJK_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk and cjk >= latin:
        return "ja"
    return "en"


def compose_answer(
    question: str,
    base_answer: str | None,
    sources: Sequence[MappingLike],
    *,
    llm_used: bool,
    is_summary: bool,
) -> str:
    lang = detect_language(question or "")
    cleaned_base = _clean_llm_answer(base_answer or "")

    if not is_summary:
        if cleaned_base:
            return cleaned_base
        fallback = _build_extractive_answer(sources, lang)
        return fallback or "Details are unavailable."

    sentences_from_base = _split_sentences(cleaned_base, lang)
    sentences_from_sources = _collect_source_sentences(sources, lang)

    chosen_sentences: list[str] = []
    if llm_used:
        chosen_sentences.extend(sentences_from_base)
    chosen_sentences.extend(sentences_from_sources)
    normalized = _dedupe_sentences(chosen_sentences, lang)
    while len(normalized) < 3:
        normalized.append(_fallback_sentence(lang))
    header = "要点:" if lang == "ja" else "Summary:"
    bullets = [_format_bullet_line(sentence, lang) for sentence in normalized[:3]]
    body = "\n".join(bullets)
    return f"{header}\n{body}".strip()


def _clean_llm_answer(answer: str) -> str:
    text = answer or ""
    text = _EN_DOC_REF_RE.sub("", text)
    text = _PAGE_REF_RE.sub("", text)
    text = text.replace("\t", " ")
    text = re.sub(r"\s*Summary:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_sentences(text: str, lang: str) -> list[str]:
    if not text:
        return []
    pattern = _SENTENCE_RE_JA if lang == "ja" else _SENTENCE_RE_EN
    sentences = [s.strip() for s in pattern.findall(text) if s.strip()]
    return sentences


def _dedupe_sentences(sentences: Sequence[str], lang: str) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for sentence in sentences:
        cleaned = _normalize_sentence(sentence)
        if not cleaned:
            continue
        normalized_key = cleaned.lower()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        unique.append(_ensure_sentence_end(cleaned, lang))
        if len(unique) >= 3:
            break
    return unique


def _ensure_sentence_end(sentence: str, lang: str) -> str:
    text = sentence.strip()
    if not text:
        return ""
    if lang == "ja":
        if not text.endswith(("。", "！", "？")):
            text = f"{text}。"
        return text
    if text[-1] not in ".!?":
        text = f"{text}."
    return text


def _collect_source_sentences(
    sources: Iterable[MappingLike], lang: str
) -> list[str]:
    sentences: list[str] = []
    seen: set[str] = set()
    for source in sources or []:
        raw = _extract_source_text(source)
        cleaned = _clean_source_text(raw)
        for sentence in _split_sentences(cleaned, lang):
            normalized = sentence.lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            sentences.append(sentence)
            if len(sentences) >= 10:
                return sentences
    return sentences


def _extract_source_text(candidate: MappingLike) -> str:
    if isinstance(candidate, dict):
        for key in ("text", "chunk_text", "snippet"):
            if candidate.get(key):
                return str(candidate[key])
        return ""
    for attr in ("text", "chunk_text", "snippet"):
        value = getattr(candidate, attr, None)
        if value:
            return str(value)
    return ""


def _clean_source_text(text: str) -> str:
    if not text:
        return ""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            line = line.replace("\t", " ")
        if _URL_RE.match(line):
            continue
        if len(line) <= 3:
            continue
        if _HEADER_RE.match(line):
            continue
        if line.lower().startswith("list of"):
            continue
        if line.lower().startswith("table of contents"):
            continue
        lines.append(line)
    collapsed = " ".join(lines)
    collapsed = re.sub(r"\s+", " ", collapsed)
    return collapsed.strip()


def _build_extractive_answer(sources: Iterable[MappingLike], lang: str) -> str:
    sentences = _collect_source_sentences(sources, lang)
    if not sentences:
        return ""
    if lang == "ja":
        return "".join(sentences[:2]).strip()
    return " ".join(sentences[:2]).strip()


def _normalize_sentence(sentence: str) -> str:
    text = (sentence or "").strip()
    if not text:
        return ""
    text = re.sub(r"^-+\s*", "", text)
    text = re.sub(r"^(summary|要点)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(" - ", " ")
    return text.strip()


def _format_bullet_line(sentence: str, lang: str) -> str:
    cleaned = sentence.strip()
    if not cleaned:
        cleaned = _fallback_sentence(lang)
    cleaned = cleaned.lstrip("- ").strip()
    return f"- {cleaned}"


def _fallback_sentence(lang: str) -> str:
    return "情報が不足しています。" if lang == "ja" else "Details are unavailable."
