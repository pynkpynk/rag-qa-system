from __future__ import annotations

import pytest

from app.api.routes import chat


class FakeSession:
    def __init__(self, results):
        self._results = list(results)

    def execute(self, stmt):
        class Result:
            def __init__(self, val):
                self._val = val

            def first(self_inner):
                return self_inner._val

        val = self._results.pop(0) if self._results else None
        return Result(val)


@pytest.fixture(autouse=True)
def reset_flags():
    chat._TRGM_AVAILABLE_FLAG = None
    chat._TRGM_UNAVAILABLE_LOGGED = False
    yield
    chat._TRGM_AVAILABLE_FLAG = None
    chat._TRGM_UNAVAILABLE_LOGGED = False


def test_trgm_detection_retries_until_true():
    sess = FakeSession([None, (True,)])
    first = chat._detect_trgm_available(sess)
    assert first is False
    second = chat._detect_trgm_available(sess)
    assert second is True
