from app.schemas.api_contract import (
    AnswerUnit,
    AnswerUnitEvidenceRef,
    Answerability,
    ChatAskResponse,
    ChatCitation,
)


def test_chat_ask_response_baseline_fields_only():
    resp = ChatAskResponse(
        answer="hello",
        citations=[ChatCitation()],
        request_id="req-123",
    )

    assert resp.answer == "hello"
    assert resp.answerability is None
    assert resp.answer_units is None


def test_chat_ask_response_with_answerability_and_units():
    answerability = Answerability(
        answerable=False,
        reason_code="INSUFFICIENT_EVIDENCE",
        reason_message="Not enough data",
        suggested_followups=["Provide more sources"],
    )

    unit = AnswerUnit(
        text="Key point one.",
        citations=[
            AnswerUnitEvidenceRef(
                source_id="S1",
                page=1,
                line_start=10,
                line_end=20,
                filename="doc.pdf",
                document_id="doc-1",
                chunk_id="chunk-1",
            )
        ],
    )

    resp = ChatAskResponse(
        answer="Key point one.",
        citations=[ChatCitation(source_id="S1")],
        request_id="req-456",
        answerability=answerability,
        answer_units=[unit],
    )

    dumped = resp.model_dump(exclude_none=True)

    assert dumped["answerability"]["reason_code"] == "INSUFFICIENT_EVIDENCE"
    assert dumped["answer_units"][0]["citations"][0]["source_id"] == "S1"
