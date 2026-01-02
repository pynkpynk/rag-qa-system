#!/usr/bin/env python3
"""
Print SET/MISSING for required backend env keys without leaking values.
"""

from __future__ import annotations

import os
from pathlib import Path

REQUIRED_KEYS = [
    "ADMIN_SUBS",
    "ADMIN_TOKEN",
    "USER_TOKEN",
    "AUTH0_DOMAIN",
    "AUTH0_AUDIENCE",
]

DEV_CONTEXT_KEYS = [
    "AUTH_MODE",
    "DEV_SUB",
    "DEV_ADMIN_SUBS",
]

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env.local"


def _load_env_file() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ENV_FILE.exists():
        return data
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        data.setdefault(key, value.strip())
    return data


def _truthy(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _effective_mode(env: dict[str, str]) -> str:
    if _truthy(env.get("AUTH_DISABLED", "")):
        return "disabled"
    mode = (env.get("AUTH_MODE", "auth0") or "auth0").lower()
    return "dev" if mode == "dev" else "auth0"


def main() -> int:
    file_env = _load_env_file()
    print(f"backend/.env.local: {'FOUND' if file_env else 'MISSING'}")
    combined = dict(os.environ)
    combined.update(file_env)
    for key in REQUIRED_KEYS:
        val = combined.get(key, "").strip()
        status = "SET" if val else "MISSING"
        print(f"{key}: {status}")
    if DEV_CONTEXT_KEYS:
        print("\n[dev-mode context]")
        for key in DEV_CONTEXT_KEYS:
            val = combined.get(key, "").strip()
            status = "SET" if val else "MISSING/EMPTY"
            print(f"{key}: {status}")
    effective_mode = _effective_mode(combined)
    allowlist_key = "DEV_ADMIN_SUBS" if effective_mode == "dev" else "ADMIN_SUBS"
    allowlist_val = combined.get(allowlist_key, "").strip()
    status = "SET" if allowlist_val else "MISSING/EMPTY"
    print("\n[admin allowlist]")
    print(f"effective_mode: {effective_mode}")
    print(f"{allowlist_key}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
