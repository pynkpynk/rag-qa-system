from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app


STREAMING_ALLOWLIST = {
    ("GET", "/api/docs/{document_id}/download"),
    ("GET", "/api/docs/{document_id}/view"),
    ("DELETE", "/api/docs/{document_id}"),  # 204 No Content
}


def test_all_json_routes_declare_response_model():
    missing: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api"):
            continue
        for method in route.methods or []:
            method_upper = method.upper()
            if method_upper in {"HEAD", "OPTIONS"}:
                continue
            key = (method_upper, route.path)
            if key in STREAMING_ALLOWLIST:
                continue
            if route.response_model is None:
                missing.append(key)
    assert not missing, f"Routes missing response_model: {missing}"
