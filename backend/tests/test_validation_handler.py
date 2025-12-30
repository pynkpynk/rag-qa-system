from __future__ import annotations

from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError

from app.main import create_app


def test_validation_handler_handles_value_error_ctx():
    app = create_app()

    @app.get("/_validation-error")
    def _raise_error():
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "foo"),
                    "msg": "boom",
                    "type": "value_error",
                    "ctx": {"error": ValueError("ctx boom")},
                }
            ]
        )

    client = TestClient(app)
    resp = client.get("/_validation-error")
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    errors = data["error"]["details"]["errors"]
    assert isinstance(errors, list)
    # Ensure ctx value is a string (not raw ValueError object)
    assert isinstance(errors[0].get("ctx", {}).get("error"), str)
