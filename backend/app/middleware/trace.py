from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class TraceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, logger_name: str = "app") -> None:
        super().__init__(app)
        self.logger_name = logger_name

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        t0 = time.time()
        try:
            response = await call_next(request)
            return response
        finally:
            t3 = time.time()
            # JSONログ（Renderで見やすい）
            log = {
                "event": "request_done",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "ms_total": int((t3 - t0) * 1000),
            }
            # printでOK（Render logsに出る）
            print(json.dumps(log, ensure_ascii=False))

    @staticmethod
    def attach_request_id(response: Response, request: Request) -> None:
        rid = getattr(request.state, "request_id", None)
        if rid:
            response.headers["x-request-id"] = rid
