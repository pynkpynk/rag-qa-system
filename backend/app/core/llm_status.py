from __future__ import annotations

import os
import sys

from app.core.config import settings


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_pytest() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def openai_key_present() -> bool:
    """
    Returns True when a non-empty OPENAI_API_KEY (or equivalent secret) is configured.
    """
    api_key_obj = getattr(settings, "openai_api_key", None)
    if api_key_obj is None:
        return False
    if hasattr(api_key_obj, "get_secret_value"):
        value = api_key_obj.get_secret_value()
    else:
        value = str(api_key_obj or "")
    return bool((value or "").strip())


def is_openai_offline() -> bool:
    """
    Determines whether the application should avoid calling OpenAI APIs.
    """
    override = os.getenv("OPENAI_OFFLINE")
    if override is not None:
        return _truthy(override)
    if getattr(settings, "openai_offline", False):
        return True
    if not openai_key_present():
        return True
    auto = (
        _truthy(os.getenv("CI")) or _truthy(os.getenv("GITHUB_ACTIONS")) or _is_pytest()
    )
    if auto:
        os.environ["OPENAI_OFFLINE"] = "1"
    return auto


def is_llm_enabled() -> bool:
    """
    Returns True only when the application is not in offline mode AND a key is present.
    """
    return openai_key_present() and not is_openai_offline()
