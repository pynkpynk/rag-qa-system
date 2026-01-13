from __future__ import annotations

from app.core.answer_composer import compose_answer, detect_language


def test_detect_language_en_vs_ja():
    assert detect_language("Please list the requirements.") == "en"
    assert detect_language("この文書の要点を教えて。") == "ja"


def test_compose_answer_formats_header_and_bullets():
    question = "List three points from the summary."
    base_answer = "First point discusses risk. Second point covers controls. Third point explains evidence."
    result = compose_answer(
        question, base_answer, [], llm_used=True, is_summary=True
    )
    lines = result.splitlines()
    assert lines[0] == "Summary:"
    bullet_lines = [line for line in lines[1:] if line.startswith("- ")]
    assert len(bullet_lines) == 3


def test_compose_answer_removes_inline_refs():
    question = "Summarize findings."
    base_answer = "The report highlights key issues [S1 p.1] and mitigations [S2 p.3]."
    result = compose_answer(
        question, base_answer, [], llm_used=True, is_summary=False
    )
    assert "[S" not in result
    assert "p." not in result.lower()


def test_compose_answer_normalizes_header_and_double_bullets():
    question = "Summarize the policy."
    base_answer = "- Summary: - First line\tSecond line.- Third"
    result = compose_answer(
        question, base_answer, [], llm_used=True, is_summary=True
    )
    lines = result.splitlines()
    assert lines[0] == "Summary:"
    assert len([ln for ln in lines[1:] if ln.startswith("- ")]) == 3


def test_compose_answer_offline_cleans_text():
    question = "要点を3点でまとめて。"
    sources = [
        {"text": "List of Figures .... 2\n概要\t第一の対策について説明する。\n"},
        {"text": "第二の対策では証跡の追跡を求める。\n第三の観点は教育プログラム。"},
    ]
    result = compose_answer(question, "", sources, llm_used=False, is_summary=True)
    assert "\t" not in result
    assert result.startswith("要点:")
    assert result.count("\n") >= 3

def test_compose_answer_factoid_falls_back_to_sources():
    question = "Who are the main contacts?"
    sources = [
        {"text": "Primary contacts include Alice and Bob for any support issues."}
    ]
    result = compose_answer(question, "", sources, llm_used=False, is_summary=False)
    assert "Alice" in result and "Bob" in result
