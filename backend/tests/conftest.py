import logging
import os
from pathlib import Path

os.environ["APP_ENV"] = "dev"
os.environ["AUTH_MODE"] = "dev"
os.environ.setdefault("DEV_SUB", "test-user")
os.environ.setdefault("OPENAI_OFFLINE", "1")

import pytest

from app.core.log_leak_scan import scan_file, format_report


@pytest.fixture(autouse=True)
def _set_default_test_env(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", os.getenv("AUTH_MODE", "dev") or "dev")
    monkeypatch.setenv("APP_ENV", os.getenv("APP_ENV", "dev") or "dev")
    monkeypatch.setenv("ALLOW_PROD_DEBUG", os.getenv("ALLOW_PROD_DEBUG", "1") or "1")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", os.getenv("RATE_LIMIT_ENABLED", "0") or "0")
    monkeypatch.setenv("MAX_REQUEST_BYTES", os.getenv("MAX_REQUEST_BYTES", "1048576") or "1048576")


@pytest.fixture(scope="session", autouse=True)
def _capture_logs_for_leak_scan():
    base_dir = Path(__file__).resolve().parents[1]
    log_dir = base_dir / ".pytest_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pytest.log"

    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        yield log_path
    finally:
        root_logger.removeHandler(handler)
        handler.close()
        violations = scan_file(log_path)
        if violations:
            report = format_report(violations)
            pytest.fail(report)
