import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.main import app as fastapi_app
from app.core.authz import Principal
from app.api.routes import chat as chat_module
from app.api.routes.chat import (
    _apply_cannot_answer_override,
    _apply_cannot_answer_override_from_units,
    _apply_offline_overlap_guard,
    _build_display_answer,
    _build_insufficient_answer,
    _compact_evidence_for_prompt,
    _attach_timing_fields,
    _recover_answer_units_with_citations,
    _ensure_debug_meta_app_env,
    _sanitize_answer_unit_texts,
    _maybe_salvage_llm_answer,
    _maybe_salvage_from_sources,
    _strip_citation_artifacts,
    _fallback_answer_units_for_insufficient_evidence,
    _is_insufficient_fallback,
    _maybe_localize_summary_answer,
    _should_enable_debug,
    _trim_units_for_sentence_request,
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


def _single_source_evidence(
    text: str,
    *,
    source_id: str = "SX",
    page: int = 1,
) -> list[dict[str, Any]]:
    return [
        {
            "source_id": source_id,
            "page": page,
            "line_start": 1,
            "line_end": 10,
            "filename": "csf.pdf",
            "document_id": f"doc-{source_id.lower()}",
            "chunk_id": f"chunk-{source_id.lower()}",
            "text": text,
        }
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


def test_unit_level_override_triggers_for_cannot_answer_message():
    units = [
        AnswerUnit(
            text="提供された資料にはTLSの最小バージョンに関する記載がないため、ここからはわかりません。",
            citations=[
                AnswerUnitEvidenceRef(
                    source_id="S1",
                    page=1,
                    line_start=5,
                    line_end=10,
                    filename="alpha.pdf",
                    document_id="doc-1",
                )
            ],
        )
    ]
    answerability = determine_answerability("question", _sample_evidence(), units)
    assert answerability.answerable is True
    updated = _apply_cannot_answer_override_from_units(units, answerability)
    assert updated.answerable is False
    assert updated.reason_code == "INSUFFICIENT_EVIDENCE"


def test_unit_level_override_does_not_flip_for_missing_only():
    units = [
        AnswerUnit(
            text="資料にはTLSの最小バージョンは記載されていません。",
            citations=[
                AnswerUnitEvidenceRef(
                    source_id="S1",
                    page=1,
                    line_start=5,
                    line_end=10,
                    filename="alpha.pdf",
                    document_id="doc-1",
                )
            ],
        )
    ]
    answerability = determine_answerability("question", _sample_evidence(), units)
    assert answerability.answerable is True
    updated = _apply_cannot_answer_override_from_units(units, answerability)
    assert updated.answerable is True


def test_offline_lexical_guard_marks_insufficient_when_no_overlap():
    question = "TLS minimum version and audit log retention"
    units = [
        AnswerUnit(
            text="Completely unrelated control summary.",
            citations=[
                AnswerUnitEvidenceRef(
                    source_id="S1",
                    page=1,
                    line_start=5,
                    line_end=10,
                    filename="alpha.pdf",
                    document_id="doc-1",
                )
            ],
        )
    ]
    answerability = determine_answerability(question, _sample_evidence(), units)
    assert answerability.answerable is True
    updated = _apply_offline_overlap_guard(
        question,
        units,
        _sample_evidence(),
        answerability,
        offline_guard_enabled=True,
    )
    assert updated.answerable is False
    assert updated.reason_code == "INSUFFICIENT_EVIDENCE"


def test_no_bullet_display_removes_key_facts_and_inline_bullets():
    question = "2文で教えて。箇条書き禁止。"
    units = [
        AnswerUnit(text="Key facts: - Foo detail.", citations=[]),
        AnswerUnit(text="- Bar insight.", citations=[]),
    ]
    display = _build_display_answer(question, units, "")
    assert "Key facts" not in display
    assert "- Foo" not in display
    assert "- Bar" not in display


def test_insufficient_fallback_units_follow_sentence_limit_no_bullets():
    question = "TLS最小バージョンと監査ログ保持を2文で。箇条書き禁止。"
    units = [
        AnswerUnit(
            text="Informative references for the CSF are listed.",
            citations=[
                AnswerUnitEvidenceRef(
                    source_id="S1",
                    page=1,
                    line_start=5,
                    line_end=8,
                    filename="alpha.pdf",
                    document_id="doc-1",
                )
            ],
        )
    ]
    answerability = determine_answerability(question, _sample_evidence(), units)
    display = _build_display_answer(question, units, "")
    assert display
    guarded = _apply_offline_overlap_guard(
        question,
        units,
        _sample_evidence(),
        answerability,
        offline_guard_enabled=True,
    )
    assert guarded.answerable is False
    fallback_units = _fallback_answer_units_for_insufficient_evidence(question)
    assert len(fallback_units) == 2
    assert all(not unit.citations for unit in fallback_units)
    fallback_answer = _build_display_answer(
        question, fallback_units, "", reason_code=guarded.reason_code
    )
    assert fallback_answer != "不明"
    assert not fallback_answer.strip().startswith("-")


def test_offline_guard_filters_generic_tokens_with_no_overlap():
    question = "CSFを一律適用する必要はありますか？箇条書き禁止。1文で。"
    units = [
        AnswerUnit(
            text="Informative references for the CSF are listed.",
            citations=[
                AnswerUnitEvidenceRef(
                    source_id="S1",
                    page=1,
                    line_start=5,
                    line_end=8,
                    filename="alpha.pdf",
                    document_id="doc-1",
                )
            ],
        )
    ]
    answerability = determine_answerability(question, _sample_evidence(), units)
    guarded = _apply_offline_overlap_guard(
        question,
        units,
        _sample_evidence(),
        answerability,
        offline_guard_enabled=True,
    )
    assert guarded.answerable is False


def test_bracket_artifacts_removed_and_fallback_not_duplicated():
    question = "オンライン資源について2文で。"
    units = [
        AnswerUnit(
            text="Online resources [ S1 ] can extend guidance 【S2】 and include annexes [S3].",
            citations=[
                AnswerUnitEvidenceRef(
                    source_id="S1",
                    page=1,
                    line_start=1,
                    line_end=5,
                    filename="alpha.pdf",
                    document_id="doc-1",
                )
            ],
        )
    ]
    display = _build_display_answer(question, units, "")
    display = _strip_citation_artifacts(display)
    assert "[" not in display and "【" not in display
    _sanitize_answer_unit_texts(question, units)
    assert "[" not in units[0].text and "【" not in units[0].text
    fallback_answer, fallback_units = _build_insufficient_answer(
        "情報不足です。3文で説明してください。"
    )
    assert "追加の資料があれば共有してください。" in fallback_answer
    assert fallback_answer.count("追加の資料があれば共有してください。") <= 1
    assert fallback_units == []


def test_insufficient_answer_returns_empty_units():
    answer, units = _build_insufficient_answer("情報不足のときは？")
    assert answer
    assert units == []
    assert _is_insufficient_fallback(answer)


def test_sentence_separator_normalization():
    question = "説明して。"
    units = [
        AnswerUnit(text="Key fact . Additional detail .", citations=[]),
    ]
    display = _build_display_answer(question, units, "")
    display = _strip_citation_artifacts(display)
    _sanitize_answer_unit_texts(question, units)
    assert " . " not in units[0].text


def test_salvage_after_insufficient_fallback():
    question = "CSF 2.0 は一律適用のアプローチを採らない、という趣旨の記述はありますか？1文で（箇条書き禁止）。"
    fallback_answer, fallback_units = _build_insufficient_answer(question)
    assert fallback_units == []
    assert _is_insufficient_fallback(fallback_answer)
    evidence = _single_source_evidence(
        "CSF 2.0 does not embrace a one-size-fits-all approach and should be tailored to specific needs.",
        source_id="S40",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert units and all(unit.citations for unit in units)
    assert " . " not in answer


def test_citation_artifacts_removed_from_answer_and_units():
    question = "Explain without bullets."
    refs = [
        AnswerUnitEvidenceRef(
            source_id="S3",
            page=7,
            line_start=1,
            line_end=17,
            filename="gamma.pdf",
            document_id="doc-3",
        )
    ]
    units = [
        AnswerUnit(text="Key facts: Control guidance (p7 L1-17) S3", citations=refs)
    ]
    display = _build_display_answer(question, units, "")
    display = _strip_citation_artifacts(display)
    _sanitize_answer_unit_texts(question, units)
    assert "S3" not in display
    assert "(p7" not in display
    assert "S3" not in units[0].text
    assert "(p7" not in units[0].text


def test_citation_recovery_attaches_sources_when_missing():
    question = "1 sentence please, no bullet points."
    answer_text = "The framework is not prescriptive and supports privacy protection."
    evidence = [
        {
            "source_id": "S10",
            "page": 4,
            "line_start": 12,
            "line_end": 20,
            "filename": "privacy.pdf",
            "document_id": "doc-10",
            "chunk_id": "chunk-10",
            "text": "This section notes the framework is not prescriptive and highlights privacy considerations.",
        },
        {
            "source_id": "S11",
            "page": 5,
            "line_start": 1,
            "line_end": 8,
            "filename": "supply.pdf",
            "document_id": "doc-11",
            "chunk_id": "chunk-11",
            "text": "Supply chain requirements are also discussed.",
        },
    ]
    recovered = _recover_answer_units_with_citations(
        question, answer_text, [], evidence, enabled=True
    )
    assert recovered
    assert recovered[0].citations
    _sanitize_answer_unit_texts(question, recovered)
    display = _build_display_answer(question, recovered, answer_text)
    display = _strip_citation_artifacts(display)
    assert not display.startswith("-")
    answerability = determine_answerability(question, evidence, recovered)
    assert answerability.answerable is True


def test_salvage_non_prescriptive_question():
    question = "CSFは具体的な実装手段を規定しないことを1文で（箇条書き禁止）教えて。"
    evidence = [
        {
            "source_id": "S20",
            "page": 2,
            "line_start": 5,
            "line_end": 12,
            "filename": "csf.pdf",
            "document_id": "doc-20",
            "chunk_id": "chunk-20",
            "text": "The CSF does not prescribe how outcomes should be achieved; organizations choose their own implementations.",
        }
    ]
    result = _maybe_salvage_llm_answer(
        question,
        evidence,
        llm_answer_used=True,
        llm_enabled=True,
    )
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 1
    assert units[0].citations
    assert not answer.startswith("-")
    assert "CSF" in answer


def test_salvage_enterprise_risk_question():
    question = "サプライチェーンやプライバシー等も含めて企業リスクとして扱う必要がありますか？2文で。箇条書き禁止。"
    evidence = [
        {
            "source_id": "S21",
            "page": 3,
            "line_start": 1,
            "line_end": 15,
            "filename": "csf.pdf",
            "document_id": "doc-21",
            "chunk_id": "chunk-21",
            "text": "Use cybersecurity risks alongside other enterprise risks including privacy, supply chain, financial, and reputational considerations.",
        }
    ]
    result = _maybe_salvage_llm_answer(
        question,
        evidence,
        llm_answer_used=True,
        llm_enabled=True,
    )
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert "サプライチェーン" in answer
    assert not answer.startswith("-")


def test_salvage_one_size_fits_all_question():
    question = "CSF 2.0 は一律適用のアプローチを採らないと聞きました。箇条書き禁止で1文で教えて。"
    evidence = [
        {
            "source_id": "S22",
            "page": 4,
            "line_start": 10,
            "line_end": 18,
            "filename": "csf.pdf",
            "document_id": "doc-22",
            "chunk_id": "chunk-22",
            "text": "Regardless of how it is applied, the CSF prompts its users to consider their cybersecurity posture in context and then adapt the CSF to their specific needs.",
        }
    ]
    result = _maybe_salvage_llm_answer(
        question,
        evidence,
        llm_answer_used=True,
        llm_enabled=True,
    )
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert answerability.reason_code != "INSUFFICIENT_EVIDENCE"
    assert len(units) == 1
    assert units[0].citations
    assert "一律" in answer
    assert "[S" not in answer
    assert " . " not in answer
    assert answer.count("。") == 1


def test_salvage_governance_question():
    question = "ガバナンスにおける注意点を箇条書き禁止で2文で示して。"
    evidence = [
        {
            "source_id": "S23",
            "page": 5,
            "line_start": 1,
            "line_end": 16,
            "filename": "csf.pdf",
            "document_id": "doc-23",
            "chunk_id": "chunk-23",
            "text": "Boards of directors should integrate cybersecurity into governance, using Profiles and Tiers to align with enterprise risk management.",
        }
    ]
    result = _maybe_salvage_llm_answer(
        question,
        evidence,
        llm_answer_used=True,
        llm_enabled=True,
    )
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert "ガバナンス" in answer
    assert not answer.startswith("-")
    assert " . " not in answer


def test_source_salvage_one_size_question():
    question = "CSF 2.0 は一律適用のアプローチを採らない、という趣旨の記述はありますか？1文で（箇条書き禁止）。"
    evidence = _single_source_evidence(
        "Regardless of how it is applied, the CSF prompts its users to consider their cybersecurity posture in context and then adapt the CSF to their specific needs.",
        source_id="S30",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert answerability.reason_code != "INSUFFICIENT_EVIDENCE"
    assert len(units) == 1
    assert units[0].citations
    assert "一律" in answer
    assert "[S" not in answer
    assert " . " not in answer
    assert answer.count("。") == 1


def test_source_salvage_exec_board_question():
    question = "経営層・取締役会とのコミュニケーションで意図している点は？2文で。"
    evidence = _single_source_evidence(
        "The CSF provides a common language for executives and boards of directors to communicate about cybersecurity outcomes and priorities.",
        source_id="S31",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert answer.count("。") == 2
    assert not answer.startswith("-")
    assert " . " not in answer


def test_source_salvage_online_resources_question():
    question = "オンライン資源（Informative References等）の扱いは？2文で。"
    evidence = _single_source_evidence(
        "Informative References map CSF outcomes to other standards, Implementation Examples offer illustrative actions, and Quick Start Guides help organizations adopt the CSF.",
        source_id="S32",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert "[S" not in answer
    assert answer.count("。") == 2
    assert " . " not in answer


def test_source_salvage_audience_question():
    question = "CSF 2.0 の想定利用者（誰に向けて書かれているか）を1文で。"
    evidence = _single_source_evidence(
        "The CSF is intended for a broad audience across public and private sectors, including organizations of all sizes.",
        source_id="S33",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 1
    assert units[0].citations
    assert "組織" in answer
    assert not answer.startswith("-")
    assert answer.count("。") == 1
    assert " . " not in answer


def test_source_salvage_profiles_tiers_question():
    question = "CSFのProfileとTierはガバナンス上どう使う？2文で。"
    evidence = _single_source_evidence(
        "CSF Organizational Profiles describe current and target states, while CSF Tiers characterize the rigor of risk management and governance practices.",
        source_id="S34",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert answer.count("。") == 2
    assert "Profile" not in answer
    assert " . " not in answer


def test_source_salvage_supply_chain_privacy_question():
    question = "サプライチェーンやプライバシー等、サイバー以外のリスクとの関係はどう述べている？2文で。"
    evidence = _single_source_evidence(
        "Every organization faces numerous types of ICT risk, including privacy, supply chain, and artificial intelligence considerations, and should integrate CSF use with ERM while some risks may be managed separately. Supply chain risk oversight and communications plus PRAM and C-SCRM practices provide a systematic process for addressing these risks.",
        source_id="S35",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert answerability.reason_code != "INSUFFICIENT_EVIDENCE"
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert answer.count("。") == 2
    assert " . " not in answer


def test_source_salvage_outcomes_question():
    question = "CSFは『成果(Outcomes)』中心ってどういう意味？2文で。"
    evidence = _single_source_evidence(
        "Outcomes are sector-, country-, and technology-neutral, providing flexibility for organizations to consider their unique risks, missions, legal requirements, and risk appetites. Each outcome is mapped directly to a list of potential security controls so implementation can vary without losing consistency.",
        source_id="S36",
    )
    result = _maybe_salvage_from_sources(question, evidence)
    assert result is not None
    answer, units, answerability = result
    assert answerability.answerable is True
    assert answerability.reason_code == "OTHER"
    assert len(units) == 2
    assert all(unit.citations for unit in units)
    assert answer.count("。") == 2
    assert " . " not in answer


def test_compact_evidence_limits_chars_and_keeps_keyword(monkeypatch):
    monkeypatch.setattr(chat_module, "EVIDENCE_MAX_CHARS_PER_SOURCE", 120)
    monkeypatch.setattr(chat_module, "EVIDENCE_MAX_CHARS_TOTAL", 200)
    question = "ガバナンスにおける注意点を要約して。"
    long_text = "\n".join(
        ["Noise sentence {}".format(i) for i in range(20)]
        + [
            "Boards of directors should integrate cybersecurity into governance using Profiles and Tiers to align with enterprise risk management."
        ]
        + ["Trailing filler {}".format(i) for i in range(10)]
    )
    rows = [
        {
            "id": "chunk-comp-1",
            "document_id": "doc-comp-1",
            "filename": "csf.pdf",
            "page": 10,
            "text": long_text,
        }
    ]
    compacted = _compact_evidence_for_prompt(question, rows)
    assert len(compacted) == 1
    snippet = compacted[0]["text"]
    assert snippet
    assert len(snippet) <= 120
    assert "Boards of directors" in snippet
    assert " . " not in snippet


def test_compact_evidence_respects_total_budget_and_is_deterministic(monkeypatch):
    monkeypatch.setattr(chat_module, "EVIDENCE_MAX_CHARS_PER_SOURCE", 80)
    monkeypatch.setattr(chat_module, "EVIDENCE_MAX_CHARS_TOTAL", 100)
    question = "オンライン資源の扱いは？"
    rows = [
        {
            "id": "chunk-comp-2",
            "document_id": "doc-comp-2",
            "filename": "csf.pdf",
            "page": 12,
            "text": "Informative References map CSF outcomes to other standards. Implementation Examples and Quick Start Guides help organizations adopt the CSF quickly.",
        },
        {
            "id": "chunk-comp-3",
            "document_id": "doc-comp-3",
            "filename": "csf.pdf",
            "page": 13,
            "text": "Additional background appendix text that should only appear if budget allows.",
        },
    ]
    first = _compact_evidence_for_prompt(question, rows)
    second = _compact_evidence_for_prompt(question, rows)
    assert first == second
    total_chars = sum(len(entry["text"]) for entry in first)
    assert total_chars <= 100
    assert any("Informative References" in entry["text"] for entry in first)
    assert all(" . " not in entry["text"] for entry in first)


def test_dev_debug_query_param_adds_timing_fields():
    allowed = _should_enable_debug(False, True, True)
    assert allowed is True
    resp: dict[str, Any] = {
        "retrieval_debug": {},
        "debug_meta": _ensure_debug_meta_app_env({"feature_flag_enabled": True}),
    }
    stage_timings = {"retrieval": 5, "llm": 10, "salvage": 0, "post": 3}
    total_start = time.perf_counter()
    _attach_timing_fields(
        resp,
        stage_timings,
        total_start=total_start,
        allowed=allowed,
    )
    for key in ("retrieval_ms", "llm_ms", "salvage_ms", "post_ms", "total_ms"):
        assert key in resp
        assert isinstance(resp[key], int)
        assert resp[key] >= 0
    assert resp["debug_meta"]["app_env"]


def test_debug_meta_env_populated(monkeypatch):
    monkeypatch.setattr(chat_module.settings, "app_env", "devlocal")
    meta = _ensure_debug_meta_app_env({"feature_flag_enabled": True})
    assert meta["app_env"] == "devlocal"


def test_chat_ask_endpoint_includes_timing_when_debug(monkeypatch):
    class FakeDB:
        def commit(self):
            return None

        def close(self):
            return None

        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return []

        def get(self, *args, **kwargs):
            return None

    class FakePrincipal:
        sub = "tester"

    monkeypatch.setattr(chat_module.settings, "app_env", "dev")
    monkeypatch.setattr(chat_module, "ENABLE_RETRIEVAL_DEBUG", True)
    monkeypatch.setattr(chat_module, "effective_auth_mode", lambda: "dev")
    monkeypatch.setattr(chat_module, "_debug_allowed_in_env", lambda: True)
    monkeypatch.setattr(
        chat_module,
        "should_include_retrieval_debug",
        lambda payload_debug, is_admin_debug: payload_debug,
    )
    monkeypatch.setattr(chat_module, "is_admin", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_module, "is_admin_debug", lambda *_a, **_k: True)
    monkeypatch.setattr(chat_module, "admin_debug_via_token", lambda *_a, **_k: False)
    monkeypatch.setattr(chat_module, "_refresh_retrieval_debug_flags", lambda: None)
    monkeypatch.setattr(chat_module, "embed_query", lambda *_a, **_k: [0.0])
    monkeypatch.setattr(chat_module, "fetch_chunks", lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(
        chat_module, "filter_noise_candidates", lambda rows, *_a, **_k: rows
    )
    monkeypatch.setattr(chat_module, "is_llm_enabled", lambda: False)

    app = FastAPI()

    @app.post("/api/chat/ask")
    def ask_route(payload: chat_module.AskPayload, request: Request):
        return chat_module.ask(payload, request, db=FakeDB(), p=FakePrincipal())

    client = TestClient(app)
    debug_resp = client.post("/api/chat/ask?debug=1", json={"question": "Test?"})
    assert debug_resp.status_code == 200
    debug_data = debug_resp.json()
    for key in ("retrieval_ms", "llm_ms", "salvage_ms", "post_ms", "total_ms"):
        assert key in debug_data
        assert isinstance(debug_data[key], int)
        assert debug_data[key] >= 0
    assert debug_data["debug_meta"]["app_env"] == "dev"
    assert isinstance(debug_data["debug_meta"].get("pid"), int)
    assert debug_data["debug_meta"]["pid"] > 0
    assert debug_data["debug_meta"]["debug_requested"] is True
    assert debug_data["debug_meta"]["debug_enabled"] is True
    assert isinstance(debug_data["debug_meta"].get("chat_file"), str)
    assert debug_data["debug_meta"]["chat_file"]
    assert isinstance(debug_data["retrieval_debug"], dict)
    assert debug_data["retrieval_debug"]
    body_debug_resp = client.post(
        "/api/chat/ask", json={"question": "Body flag?", "debug": True}
    )
    assert body_debug_resp.status_code == 200
    body_debug_data = body_debug_resp.json()
    for key in ("retrieval_ms", "llm_ms", "salvage_ms", "post_ms", "total_ms"):
        assert key in body_debug_data
        assert isinstance(body_debug_data[key], int)
        assert body_debug_data[key] >= 0
    assert body_debug_data["debug_meta"]["debug_requested"] is True
    assert body_debug_data["debug_meta"]["debug_enabled"] is True

    no_debug_resp = client.post("/api/chat/ask", json={"question": "Test?"})
    assert no_debug_resp.status_code == 200
    no_debug_data = no_debug_resp.json()
    for key in ("retrieval_ms", "llm_ms", "salvage_ms", "post_ms", "total_ms"):
        assert key not in no_debug_data


def test_chat_ask_debug_query_returns_placeholders_when_disabled(monkeypatch):
    class FakeDB:
        def commit(self):
            return None

        def close(self):
            return None

        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return []

        def get(self, *args, **kwargs):
            return None

    class FakePrincipal:
        sub = "tester"

    monkeypatch.setattr(chat_module.settings, "app_env", "prod")
    monkeypatch.setattr(chat_module, "ENABLE_RETRIEVAL_DEBUG", True)
    monkeypatch.setattr(chat_module, "effective_auth_mode", lambda: "prod")
    monkeypatch.setattr(chat_module, "_debug_allowed_in_env", lambda: False)
    monkeypatch.setattr(
        chat_module,
        "should_include_retrieval_debug",
        lambda payload_debug, is_admin_debug: False,
    )
    monkeypatch.setattr(chat_module, "is_admin", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(chat_module, "is_admin_debug", lambda *_a, **_k: False)
    monkeypatch.setattr(chat_module, "admin_debug_via_token", lambda *_a, **_k: False)
    monkeypatch.setattr(chat_module, "_refresh_retrieval_debug_flags", lambda: None)
    monkeypatch.setattr(chat_module, "embed_query", lambda *_a, **_k: [0.0])
    monkeypatch.setattr(chat_module, "fetch_chunks", lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(
        chat_module, "filter_noise_candidates", lambda rows, *_a, **_k: rows
    )
    monkeypatch.setattr(chat_module, "is_llm_enabled", lambda: False)

    app = FastAPI()

    @app.post("/api/chat/ask")
    def ask_route(payload: chat_module.AskPayload, request: Request):
        return chat_module.ask(payload, request, db=FakeDB(), p=FakePrincipal())

    client = TestClient(app)
    debug_resp = client.post("/api/chat/ask?debug=1", json={"question": "Test?"})
    assert debug_resp.status_code == 200
    data = debug_resp.json()
    assert data["debug_meta"] == {}
    assert data["retrieval_debug"] == {}
    for key in ("retrieval_ms", "llm_ms", "salvage_ms", "post_ms", "total_ms"):
        assert key not in data


def test_display_answer_strips_bullets_and_markers():
    units = [
        AnswerUnit(text="- First point [S1] (p2)", citations=[]),
        AnswerUnit(text="- Second point [S2]", citations=[]),
    ]
    result = _build_display_answer("question", units, "- fallback [S1]")
    assert result == "First point Second point"


def test_sentence_limit_request_trims_units_and_answer():
    units = [
        AnswerUnit(text="Sentence one.", citations=[]),
        AnswerUnit(text="Sentence two.", citations=[]),
        AnswerUnit(text="Sentence three.", citations=[]),
    ]
    trimmed = _trim_units_for_sentence_request("Please answer in 2 sentences", units)
    assert len(trimmed) == 2
    display = _build_display_answer("Please answer in 2 sentences", trimmed, "")
    assert "Sentence three" not in display


def test_bullet_request_keeps_bullet_formatting():
    units = [
        AnswerUnit(text="Alpha insight.", citations=[]),
        AnswerUnit(text="Beta insight.", citations=[]),
    ]
    display = _build_display_answer("Provide bullet list", units, "")
    assert display.startswith("- ")
    assert "\n" in display


def test_no_bullet_request_with_sentence_limit_keeps_units():
    question = "Please answer in 2 sentences, no bullet points."
    answer = "- TLS minimum [S1]\n- Audit logging retention [S2]"
    evidence = _sample_evidence()
    units = build_answer_units_for_response(answer, evidence)
    trimmed = _trim_units_for_sentence_request(question, units)
    assert len(trimmed) >= 1
    answerability = determine_answerability(question, evidence, trimmed)
    display = _build_display_answer(
        question, trimmed, answer, reason_code=answerability.reason_code
    )
    assert not display.startswith("-")
    assert len(trimmed) == 2


def test_trim_units_never_returns_empty_when_limit_positive(monkeypatch):
    monkeypatch.setattr(
        chat_module, "_sentence_limit_from_question", lambda _q: 1
    )
    units = [
        AnswerUnit(text="Sentence one.", citations=[]),
        AnswerUnit(text="Sentence two.", citations=[]),
    ]
    trimmed = _trim_units_for_sentence_request("ignored", units)
    assert len(trimmed) == 1


def test_display_answer_uses_cleaned_fallback_when_units_missing():
    display = _build_display_answer("question", [], "- Fallback [S1]")
    assert display == "Fallback"


def test_display_answer_returns_reason_message_when_empty():
    message = _build_display_answer(
        "提供された資料からは？", [], "", reason_code="INSUFFICIENT_EVIDENCE"
    )
    assert message == "提示された資料からは確認できません。"


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
