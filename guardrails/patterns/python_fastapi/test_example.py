from __future__ import annotations

import pytest

pytest.skip(
    "Guardrails template file; not part of this project's test suite.",
    allow_module_level=True,
)

from patterns.python_fastapi.service import get_health


def test_get_health_returns_ok():
    result = get_health()
    assert result.status == "ok"
