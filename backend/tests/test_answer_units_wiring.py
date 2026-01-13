from app.api.routes.chat import (
    build_answer_units_for_response,
    determine_answerability,
)


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
