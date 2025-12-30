from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.core.authz import effective_auth_mode
from app.schemas.api_contract import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    git_sha = os.getenv("GIT_SHA") or os.getenv("BUILD_ID") or "unknown"
    return {
        "app": "RAG QA System",
        "version": "0.1.0",
        "status": "ok",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "app_env": getattr(settings, "app_env", "dev"),
        "auth_mode": effective_auth_mode(),
        "git_sha": git_sha,
    }
