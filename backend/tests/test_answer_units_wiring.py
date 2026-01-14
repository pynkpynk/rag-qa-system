import json

from app.api.routes import chat as chat_module
from app.api.routes.chat import (
    _apply_cannot_answer_override,
    _maybe_localize_summary_answer,
    build_answer_units_for_response,
    determine_answerability,
    inline_annotation_from_refs,
)
from app.schemas.api_contract import AnswerUnit, AnswerUnitEvidenceRef


def _sample_evidence():
    return [
        {
            "source_id": "S1",
            "page": 1,
            "line_start": 5,
            "line_end": 15,
            "filename": "alpha.pdf",
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "text": "Alpha chunk",
        },
        {
            "source_id": "S2",
            "page": 2,
            "line_start": 20,
            "line_end": 30,
            "filename": "beta.pdf",
            "document_id": "doc-2",
            "chunk_id": "chunk-2",
            "text": "Beta chunk",
        },
    ]


def test_build_answer_units_maps_citations():
    answer = "- Point A [S1]\n- Point B [S2]"
    units = build_answer_units_for_response(answer, _sample_evidence())
    assert len(units) == 2
    assert units[0].citations and units[0].citations[0].source_id == "S1"
    assert units[1].citations and units[1].citations[0].source_id == "S2"


def test_answerability_detects_missing_sources():
    answer = "- Point A no cite"
    units = build_answer_units_for_response(answer, [])
    answerability = determine_answerability("question", [], units)
    assert answerability.answerable is False
    assert answerability.reason_code == "NO_SOURCES"


def test_units_inherit_previous_citation_when_missing():
    answer = "- Intro [S1]\n- Follow up sentence without cite"
    units = build_answer_units_for_response(answer, _sample_evidence())
    assert len(units) == 2
    assert units[1].citations and units[1].citations[0].source_id == "S1"
    answerability = determine_answerability("question", _sample_evidence(), units)
    assert answerability.answerable is True


def test_units_match_best_source_text():
    evidence = [
        {
            "source_id": "S3",
            "page": 7,
            "line_start": 30,
            "line_end": 45,
            "filename": "gamma.pdf",
            "document_id": "doc-3",
            "chunk_id": "chunk-3",
            "text": "Gamma finding mentions escalation runbooks and approvals.",
        },
        {
            "source_id": "S4",
            "page": 2,
            "line_start": 5,
            "line_end": 15,
            "filename": "delta.pdf",
            "document_id": "doc-4",
            "chunk_id": "chunk-4",
            "text": "Delta overview: governance structure prioritizes transparency.",
        },
        {
            "source_id": "S5",
            "page": 5,
            "line_start": 20,
            "line_end": 32,
            "filename": "epsilon.pdf",
            "document_id": "doc-5",
            "chunk_id": "chunk-5",
            "text": "Epsilon section highlights control testing cadence and reviewers.",
        },
    ]
    answer = "\n".join(
        [
            "- Governance structure prioritizes transparency.",
            "- Control testing cadence and reviewers are defined.",
            "- Escalation runbooks require approvals.",
        ]
    )
    units = build_answer_units_for_response(answer, evidence)
    assert len(units) == 3
    assert units[0].citations and units[0].citations[0].source_id == "S4"
    assert units[1].citations and units[1].citations[0].source_id == "S5"
    assert units[2].citations and units[2].citations[0].source_id == "S3"


def test_inline_annotation_helper_formats_page_and_lines():
    refs = [
        AnswerUnitEvidenceRef(
            source_id="S9",
            page=7,
            line_start=10,
            line_end=18,
            filename="delta.pdf",
            document_id="doc-9",
        )
    ]
    assert inline_annotation_from_refs(refs) == "(p7 L10-18)"

    refs_short = [
        AnswerUnitEvidenceRef(
            source_id="S10",
            page=3,
            filename="epsilon.pdf",
            document_id="doc-10",
        )
    ]
    assert inline_annotation_from_refs(refs_short) == "(p3)"


def test_summary_rewrite_skipped_in_offline_mode(monkeypatch):
    tracker = {"called": False}

    def _fake_call_llm(*args, **kwargs):
        tracker["called"] = True
        raise AssertionError("call_llm should not execute in offline mode")

    monkeypatch.setattr(chat_module, "call_llm", _fake_call_llm)
    unit = AnswerUnit(
        text="- 要約 [S1]",
        citations=[
            AnswerUnitEvidenceRef(
                source_id="S1",
                page=1,
                line_start=2,
                line_end=6,
                filename="alpha.pdf",
                document_id="doc-1",
            )
        ],
    )
    answer, units = _maybe_localize_summary_answer(
        question="要約して",
        answer_text=unit.text,
        answer_units=[unit],
        source_evidence=_sample_evidence(),
        summary_request=True,
        llm_enabled=False,
        offline_mode=True,
        model="gpt-5-mini",
        gen={},
    )
    assert tracker["called"] is False
    assert answer == unit.text
    assert len(units) == 1
    assert units[0].text == unit.text
    assert units[0].citations and units[0].citations[0].source_id == "S1"


def test_unknown_answer_forces_answerability_false_en():
    evidence = _sample_evidence()
    answer = "- I don't know based on the provided sources."
    units = build_answer_units_for_response(answer, evidence)
    answerability = determine_answerability("question", evidence, units)
    assert answerability.answerable is True
    updated = _apply_cannot_answer_override(
        "I don't know based on the provided sources.", answerability
    )
    assert updated.answerable is False
    assert updated.reason_code == "INSUFFICIENT_EVIDENCE"


def test_unknown_answer_forces_answerability_false_ja():
    evidence = _sample_evidence()
    answer = "- 提供された資料からは判断できません。"
    units = build_answer_units_for_response(answer, evidence)
    answerability = determine_answerability("question", evidence, units)
    assert answerability.answerable is True
    updated = _apply_cannot_answer_override(
        "提供された資料からは判断できません。", answerability
    )
    assert updated.answerable is False
    assert updated.reason_code == "INSUFFICIENT_EVIDENCE"


def test_unknown_answer_forces_answerability_false_en_variant():
    evidence = _sample_evidence()
    units = build_answer_units_for_response("- Valid [S1]", evidence)
    answerability = determine_answerability("question", evidence, units)
    updated = _apply_cannot_answer_override(
        "I can't answer based on the provided materials.", answerability
    )
    assert updated.answerable is False
    assert updated.reason_code == "INSUFFICIENT_EVIDENCE"


def test_unknown_answer_forces_answerability_false_ja_variant():
    evidence = _sample_evidence()
    units = build_answer_units_for_response("- Valid [S1]", evidence)
    answerability = determine_answerability("question", evidence, units)
    updated = _apply_cannot_answer_override(
        "提供された参照資料には具体的な手順が含まれていないため、要約できません。", answerability
    )
    assert updated.answerable is False
    assert updated.reason_code == "INSUFFICIENT_EVIDENCE"


def test_missing_info_without_cannot_signal_does_not_flip():
    evidence = _sample_evidence()
    units = build_answer_units_for_response("- Valid [S1]", evidence)
    answerability = determine_answerability("question", evidence, units)
    updated = _apply_cannot_answer_override(
        "資料には記述が含まれていませんが、他の情報を確認してください。", answerability
    )
    assert updated.answerable is True


def test_sentence_splitting_assigns_evidence_en():
    evidence = [
        {
            "source_id": "S10",
            "page": 3,
            "line_start": 5,
            "line_end": 12,
            "filename": "alpha.pdf",
            "document_id": "doc-10",
            "chunk_id": "chunk-10",
            "text": "Sentence one explains policy controls in detail.",
        },
        {
            "source_id": "S11",
            "page": 4,
            "line_start": 8,
            "line_end": 18,
            "filename": "beta.pdf",
            "document_id": "doc-11",
            "chunk_id": "chunk-11",
            "text": "Sentence two describes the audit requirements.",
        },
    ]
    answer = "Sentence one explains policy controls in detail. Sentence two describes the audit requirements."
    units = build_answer_units_for_response(answer, evidence)
    assert len(units) == 2
    assert units[0].citations and units[0].citations[0].source_id == "S10"
    assert units[1].citations and units[1].citations[0].source_id == "S11"


def test_sentence_splitting_assigns_evidence_ja():
    evidence = [
        {
            "source_id": "S12",
            "page": 1,
            "line_start": 1,
            "line_end": 5,
            "filename": "gamma.pdf",
            "document_id": "doc-12",
            "chunk_id": "chunk-12",
            "text": "一文目です。ガバナンスを説明します。",
        },
        {
            "source_id": "S13",
            "page": 2,
            "line_start": 10,
            "line_end": 18,
            "filename": "delta.pdf",
            "document_id": "doc-13",
            "chunk_id": "chunk-13",
            "text": "二文目です。手順を示します。",
        },
    ]
    answer = "一文目です。二文目です。"
    units = build_answer_units_for_response(answer, evidence)
    assert len(units) == 2
    assert units[0].citations and units[0].citations[0].source_id == "S12"
    assert units[1].citations and units[1].citations[0].source_id == "S13"


def test_bullet_multi_sentence_inherits_citation_when_needed():
    evidence = [
        {
            "source_id": "S14",
            "page": 6,
            "line_start": 2,
            "line_end": 9,
            "filename": "epsilon.pdf",
            "document_id": "doc-14",
            "chunk_id": "chunk-14",
            "text": "First sentence cites a specific control.",
        }
    ]
    answer = "- First sentence cites a specific control. Second sentence adds context."
    units = build_answer_units_for_response(answer, evidence)
    assert len(units) == 2
    assert units[0].citations and units[0].citations[0].source_id == "S14"
    assert units[1].citations and units[1].citations[0].source_id == "S14"


def test_localized_units_preserve_citations(monkeypatch):
    evidence = [
        {
            "source_id": "S1",
            "page": 2,
            "line_start": 1,
            "line_end": 9,
            "filename": "alpha.pdf",
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "text": "Alpha section covers governance basics.",
        },
        {
            "source_id": "S2",
            "page": 5,
            "line_start": 12,
            "line_end": 22,
            "filename": "beta.pdf",
            "document_id": "doc-2",
            "chunk_id": "chunk-2",
            "text": "Beta section covers controls cadence.",
        },
        {
            "source_id": "S3",
            "page": 7,
            "line_start": 3,
            "line_end": 15,
            "filename": "gamma.pdf",
            "document_id": "doc-3",
            "chunk_id": "chunk-3",
            "text": "Gamma section covers escalation.",
        },
    ]
    answer = "- Governance basics [S1]\n- Controls cadence [S2]\n- Escalation steps [S3]"
    units = build_answer_units_for_response(answer, evidence)
    localized_lines = [
        "- ガバナンスの基本 [S1]",
        "- 管理サイクル [S2]",
        "- エスカレーション手順 [S3]",
    ]

    monkeypatch.setattr(
        chat_module,
        "call_llm",
        lambda *args, **kwargs: json.dumps(localized_lines),
    )
    monkeypatch.setattr(chat_module, "is_openai_offline", lambda: False)

    new_answer, new_units = _maybe_localize_summary_answer(
        question="要約して",
        answer_text=answer,
        answer_units=units,
        source_evidence=evidence,
        summary_request=True,
        llm_enabled=True,
        offline_mode=False,
        model="gpt-5-mini",
        gen={},
    )

    assert len(new_units) == len(units)
    for original, updated in zip(units, new_units):
        assert updated.text != original.text
        assert updated.citations == original.citations
        assert updated.citations[0].page == original.citations[0].page

    assert "要点" in new_answer
    assert "ガバナンス" in new_answer
