from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.db.capabilities import DBCapabilities


def test_health_includes_db_capabilities():
    client = TestClient(main_mod.app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    caps = resp.json().get("db_capabilities")
    assert isinstance(caps, dict)
    assert "pg_trgm_available" in caps
    assert "vector_available" in caps
    assert "checked_ok" in caps


def test_strict_mode_missing_extensions_fails(monkeypatch):
    def fake_detect(engine, required_extensions=None):
        missing = list(required_extensions or ["pg_trgm"])
        return DBCapabilities(
            extensions_present=[],
            pg_trgm_available=False,
            vector_available=False,
            checked_ok=True,
            error=None,
            missing_required_extensions=missing,
        )

    monkeypatch.setenv("DB_CAPS_STRICT", "1")
    monkeypatch.setenv("DB_REQUIRED_EXTENSIONS", "pg_trgm")
    monkeypatch.setattr(
        "app.db.capabilities.detect_db_capabilities", fake_detect
    )

    with pytest.raises(RuntimeError):
        main_mod.create_app()
