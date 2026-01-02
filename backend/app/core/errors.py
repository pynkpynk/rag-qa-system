from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR


def err(code: str, message: str, status: int, details: dict | None = None):
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status, content=payload)


async def http_exception_handler(request: Request, exc: HTTPException):
    # detail に {code,message,details} が入っていればそれを採用
    if (
        isinstance(exc.detail, dict)
        and "code" in exc.detail
        and "message" in exc.detail
    ):
        payload = {"error": exc.detail}
        return JSONResponse(status_code=exc.status_code, content=payload)
    return err("HTTP_ERROR", str(exc.detail), exc.status_code)


async def unhandled_exception_handler(request: Request, exc: Exception):
    # ここでログに request_id を出すのは middleware 側でやる
    return err(
        "INTERNAL_ERROR", "Internal server error.", HTTP_500_INTERNAL_SERVER_ERROR
    )
