from __future__ import annotations

import os
import re
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _max_request_bytes() -> int:
    default = 262_144 if (os.getenv("APP_ENV", "dev") == "prod") else 1_048_576
    try:
        return int(os.getenv("MAX_REQUEST_BYTES", default))
    except ValueError:
        return default


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers") or []
        inbound: str | None = None
        for key, value in headers:
            if key.lower() == b"x-request-id":
                inbound = value.decode("latin-1")
                break

        if inbound and REQUEST_ID_RE.match(inbound):
            request_id = inbound
        else:
            request_id = str(uuid.uuid4())

        scope.setdefault("state", {})["request_id"] = request_id
        rid_bytes = request_id.encode("ascii", "ignore")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                filtered = [
                    (k, v)
                    for (k, v) in message.get("headers", [])
                    if k.lower() != b"x-request-id"
                ]
                filtered.append((b"x-request-id", rid_bytes))
                message["headers"] = filtered
            await send(message)

        await self.app(scope, receive, send_wrapper)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, headers: dict[str, str] | None = None):
        super().__init__(app)
        self.headers = headers or {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "interest-cohort=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-site",
        }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in self.headers.items():
            response.headers.setdefault(key, value)
        return response


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "").upper()
        if method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        limit = _max_request_bytes()
        if limit <= 0:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length.decode("latin-1")) > limit:
                    await self._send_413(send)
                    return
            except ValueError:
                pass

        buffer = bytearray()

        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"") or b""
            if chunk:
                buffer.extend(chunk)
                if len(buffer) > limit:
                    # Drain any remaining body to keep connection clean.
                    while message.get("more_body", False):
                        message = await receive()
                        if message["type"] != "http.request":
                            continue
                        if not message.get("more_body", False):
                            break
                    await self._send_413(send)
                    return
            if not message.get("more_body", False):
                break

        payload = bytes(buffer)
        sent = False

        async def replay_receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    async def _send_413(self, send: Send) -> None:
        headers = [(b"content-type", b"application/json")]
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"Request body too large"}',
                "more_body": False,
            }
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        from app.core.rate_limit import enforce_rate_limit

        self._enforce = enforce_rate_limit

    async def dispatch(self, request: Request, call_next):
        response = self._enforce(request)
        if response is not None:
            return response
        return await call_next(request)
