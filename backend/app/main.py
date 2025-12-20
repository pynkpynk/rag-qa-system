from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.api.routes.runs import router as runs_router
from app.api.routes.docs import router as docs_router
from app.api.routes.chat import router as chat_router
from app.api.routes.chunks import router as chunks_router


def _error_payload(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def create_app() -> FastAPI:
    """
    Application factory.
    - Keeps setup (CORS / routers) centralized and readable.
    - Makes future testing and extension easier.
    """
    app = FastAPI(title="RAG QA System", version="0.1.0")

    # ---- Request tracing / request_id ----
    @app.middleware("http")
    async def request_trace(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        t0 = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            # 例外は exception_handler 側でJSON化されるが、
            # middlewareで握りつぶさないようにそのまま投げる
            raise e
        finally:
            t3 = time.time()
            # JSONログ（Render logsで追いやすい）
            log = {
                "event": "request_done",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "ms_total": int((t3 - t0) * 1000),
            }
            print(json.dumps(log, ensure_ascii=False))

        response.headers["x-request-id"] = request_id
        return response

    # ---- Exception handlers (unified error JSON) ----
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # すでに detail が {code,message,details} 形式なら尊重
        if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
            payload = {"error": exc.detail}
            return JSONResponse(status_code=exc.status_code, content=payload)

        # statusから最低限のcodeを割り当て（UI側で説明しやすくする）
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
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                details={"errors": exc.errors()},
            ),
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # ここでは詳細を返しすぎない（ログで追う）
        rid = getattr(request.state, "request_id", "")
        print(json.dumps({"event": "unhandled_exception", "request_id": rid, "error": repr(exc)}, ensure_ascii=False))
        return JSONResponse(
            status_code=500,
            content=_error_payload(code="INTERNAL_ERROR", message="Internal server error."),
            headers={"x-request-id": rid},
        )

    # ---- Health ----
    @app.get("/api/health")
    def health():
        return {
            "app": app.title,
            "version": app.version,
            "status": "ok",
            "time_utc": datetime.now(timezone.utc).isoformat(),
        }

    # ---- CORS ----
    cors_origins_raw = getattr(settings, "cors_origins", "") or ""
    origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # 空だとCORS許可なし（Vercel rewriteで同一オリジンなら問題なし）
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

    return app


app = create_app()
