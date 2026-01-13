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
