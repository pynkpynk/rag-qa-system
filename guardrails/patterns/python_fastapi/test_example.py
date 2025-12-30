from __future__ import annotations

from patterns.python_fastapi.service import get_health


def test_get_health_returns_ok():
    result = get_health()
    assert result.status == "ok"
