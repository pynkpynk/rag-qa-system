import pytest
from app.schemas.chat import ChatAskRequest
from app.core.debug_sanitize import sanitize_debug

def test_message_fallback_priority():
    req = ChatAskRequest(question="  Q  ", message="M", debug=False)
    assert req.effective_query() == "Q"
    req2 = ChatAskRequest(question="   ", message="  M  ", debug=False)
    assert req2.effective_query() == "M"

def test_requires_question_or_message():
    with pytest.raises(Exception):
        ChatAskRequest(question="  ", message="  ", debug=False)

def test_debug_sanitizer_allowlist():
    raw = {
        "retrieval": {"vec_count": 1, "db_host": "secret", "principal_sub": "secret"},
        "sources": [{"sid": "S1", "doc_id": "d", "page": 1, "score": 0.1, "db_name": "secret"}],
        "db_name": "secret",
    }
    clean = sanitize_debug(raw)
    assert "db_name" not in clean
    assert "db_host" not in clean["retrieval"]
    assert "principal_sub" not in clean["retrieval"]
    assert "db_name" not in clean["sources"][0]
