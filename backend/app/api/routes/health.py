from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.core.authz import effective_auth_mode
from app.core.build_info import get_git_sha
from app.core.llm_status import is_llm_enabled, is_openai_offline, openai_key_present
from app.schemas.api_contract import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {
        "app": "RAG QA System",
        "version": "0.1.0",
        "status": "ok",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "app_env": getattr(settings, "app_env", "dev"),
        "auth_mode": effective_auth_mode(),
        "git_sha": get_git_sha(),
        "llm_enabled": is_llm_enabled(),
        "openai_offline": is_openai_offline(),
        "openai_key_present": openai_key_present(),
    }
