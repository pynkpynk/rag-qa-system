from __future__ import annotations

from app.api.routes.chat import determine_answerability
from app.schemas.api_contract import AnswerUnit


def test_refusal_like_answer_marks_unanswerable() -> None:
    answer_text = "提示された資料からは確認できません。"
    units = [AnswerUnit(text=answer_text, citations=[{"document_id": "doc-1"}])]
    answerability = determine_answerability(
        "日本語の質問ですか？",
        source_evidence=[{"document_id": "doc-1"}],
        answer_units=units,
        answer_text=answer_text,
    )
    assert answerability.answerable is False
    assert answerability.reason_code == "INSUFFICIENT_EVIDENCE"
    assert answerability.reason_message == "提示された根拠からは確認できません。"


def test_supported_answer_remains_answerable() -> None:
    answer_text = "The capital of France is Paris."
    units = [AnswerUnit(text=answer_text, citations=[{"document_id": "doc-1"}])]
    answerability = determine_answerability(
        "What is the capital of France?",
        source_evidence=[{"document_id": "doc-1"}],
        answer_units=units,
        answer_text=answer_text,
    )
    assert answerability.answerable is True
    assert answerability.reason_code == "OTHER"


def test_refusal_with_sources_phrase_marks_unanswerable() -> None:
    answer_text = "提供された情報源に基づいては分かりません。"
    units = [AnswerUnit(text=answer_text, citations=[{"document_id": "doc-1"}])]
    answerability = determine_answerability(
        "質問です。",
        source_evidence=[{"document_id": "doc-1"}],
        answer_units=units,
        answer_text=answer_text,
    )
    assert answerability.answerable is False
    assert answerability.reason_code == "INSUFFICIENT_EVIDENCE"
    assert answerability.reason_message == "提示された根拠からは確認できません。"


def test_refusal_missing_description_marks_unanswerable() -> None:
    answer_text = "提供された資料には就業規則の作成・変更手続きに関する記載がないため、要点を提示できません。"
    units = [AnswerUnit(text=answer_text, citations=[{"document_id": "doc-1"}])]
    answerability = determine_answerability(
        "就業規則の手続きを教えてください。",
        source_evidence=[{"document_id": "doc-1"}],
        answer_units=units,
        answer_text=answer_text,
    )
    assert answerability.answerable is False
    assert answerability.reason_code == "INSUFFICIENT_EVIDENCE"
    assert answerability.reason_message == "提示された根拠からは確認できません。"


def test_refusal_unknown_prefix_with_missing_text_marks_unanswerable() -> None:
    answer_text = (
        "不明：提供された資料には就業規則の作成・変更手続きに関する記載がありません。"
    )
    units = [AnswerUnit(text=answer_text, citations=[{"document_id": "doc-1"}])]
    answerability = determine_answerability(
        "就業規則の手続きを教えてください。",
        source_evidence=[{"document_id": "doc-1"}],
        answer_units=units,
        answer_text=answer_text,
    )
    assert answerability.answerable is False
    assert answerability.reason_code == "INSUFFICIENT_EVIDENCE"
    assert answerability.reason_message == "提示された根拠からは確認できません。"
