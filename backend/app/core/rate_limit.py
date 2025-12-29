from __future__ import annotations

import os
import time
from collections import deque, defaultdict
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse


RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "0") == "1"
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60") or "60")
RATE_LIMIT_WINDOW = 60.0  # seconds

_REQUEST_BUCKETS: Dict[str, Deque[float]] = defaultdict(deque)


def _rate_limit_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def enforce_rate_limit(request: Request) -> JSONResponse | None:
    if not RATE_LIMIT_ENABLED:
        return None
    if request.method != "POST" or request.url.path != "/api/chat/ask":
        return None
    limit = max(1, RATE_LIMIT_RPM)
    now = time.monotonic()
    key = _rate_limit_key(request)
    bucket = _REQUEST_BUCKETS[key]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW:
        bucket.popleft()
    if len(bucket) >= limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )
    bucket.append(now)
    return None
