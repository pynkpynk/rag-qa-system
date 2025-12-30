from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.middleware.security import (
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
)
from app.api.routes.runs import router as runs_router
from app.api.routes.docs import router as docs_router
from app.api.routes.chat import router as chat_router
from app.api.routes.chunks import router as chunks_router
from app.api.routes.debug import router as debug_router
from app.api.routes.search import router as search_router
from app.schemas.api_contract import HealthResponse


def smoke_endpoint_enabled() -> bool:
    env = os.getenv("APP_ENV", "dev").lower()
    return env in {"dev", "test"} and os.getenv("ENABLE_SMOKE_ENDPOINT", "0") == "1"


class SmokeEchoPayload(BaseModel):
    question: str
    run_id: Optional[str] = None


def _error_payload(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        entry = dict(err)
        ctx = entry.get("ctx")
        if isinstance(ctx, dict):
            safe_ctx: dict[str, Any] = {}
            for key, value in ctx.items():
                try:
                    json.dumps(value)
                    safe_ctx[key] = value
                except TypeError:
                    safe_ctx[key] = repr(value)
            entry["ctx"] = safe_ctx
        sanitized.append(entry)
    return sanitized

def normalize_http_exception_detail(detail: Any) -> Dict[str, Any] | None:
    if not isinstance(detail, dict):
        return None
    if "error" in detail and isinstance(detail["error"], dict):
        err = detail["error"]
        if isinstance(err.get("code"), str) and isinstance(err.get("message"), str):
            return detail
    if "code" in detail and "message" in detail:
        code = detail.get("code")
        message = detail.get("message")
        if isinstance(code, str) and isinstance(message, str):
            return {"error": {"code": code, "message": message}}
    return None


def create_app() -> FastAPI:
    """
    Application factory.
    - Keeps setup (CORS / routers) centralized and readable.
    - Makes future testing and extension easier.
    """
    app = FastAPI(title="RAG QA System", version="0.1.0")
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # ---- Request tracing / request_id ----
    @app.middleware("http")
    async def request_trace(request: Request, call_next):
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())

        t0 = time.time()
        try:
            response = await call_next(request)
        except Exception:
            raise
        finally:
            t3 = time.time()
            log = {
                "event": "request_done",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "ms_total": int((t3 - t0) * 1000),
            }
            print(json.dumps(log, ensure_ascii=False))

        return response

    # ---- Exception handlers (unified error JSON) ----
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        normalized = normalize_http_exception_detail(exc.detail)
        if normalized is not None:
            return JSONResponse(
                status_code=exc.status_code,
                content=normalized,
                headers={"x-request-id": getattr(request.state, "request_id", "")},
            )

        code = "HTTP_ERROR"
        if exc.status_code == 403:
            code = "RUN_FORBIDDEN"
        elif exc.status_code == 404:
            code = "NOT_FOUND"
        elif exc.status_code == 413:
            code = "FILE_TOO_LARGE"

        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code=code, message=str(exc.detail)),
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = {"errors": _sanitize_validation_errors(exc.errors())}
        payload = _error_payload(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details=details,
        )
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(payload),
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", "")
        print(json.dumps({"event": "unhandled_exception", "request_id": rid, "error": repr(exc)}, ensure_ascii=False))
        return JSONResponse(
            status_code=500,
            content=_error_payload(code="INTERNAL_ERROR", message="Internal server error."),
            headers={"x-request-id": rid},
        )

    # ---- Health ----
    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return {
            "app": app.title,
            "version": app.version,
            "status": "ok",
            "time_utc": datetime.now(timezone.utc).isoformat(),
        }

    # ---- CORS ----
    raw_origins = (
        getattr(settings, "cors_origins", None)
        or getattr(settings, "cors_origin", None)
        or ""
    )

    def _clean_origin(value: str) -> str:
        cleaned = value.strip()
        while cleaned.endswith("/") and cleaned != "/":
            cleaned = cleaned[:-1]
        return cleaned

    origins = [_clean_origin(o) for o in raw_origins.split(",") if _clean_origin(o)]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routers ----
    api_prefix = "/api"
    app.include_router(runs_router, prefix=api_prefix, tags=["runs"])
    app.include_router(docs_router, prefix=api_prefix, tags=["docs"])
    app.include_router(chat_router, prefix=api_prefix, tags=["chat"])
    app.include_router(chunks_router, prefix=api_prefix, tags=["chunks"])
    app.include_router(search_router, prefix=api_prefix, tags=["search"])  # ✅ ここで統一して追加
    app.include_router(debug_router, prefix=api_prefix, tags=["_debug"])

    if smoke_endpoint_enabled():
        @app.post("/api/_smoke/echo")
        async def smoke_echo(payload: SmokeEchoPayload):
            return {"ok": True, "echo_length": len(payload.question)}

    return app


app = create_app()
