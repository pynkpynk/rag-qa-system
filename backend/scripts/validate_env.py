#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urlparse


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    warning: bool = False


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _redact(value: str | None, prefix: int = 4, suffix: int = 2) -> str:
    if not value:
        return "<empty>"
    if len(value) <= prefix + suffix:
        return value[:prefix] + "…"
    return value[:prefix] + "…" + value[-suffix:]


def format_report(results: Iterable[CheckResult]) -> str:
    lines: list[str] = []
    for res in results:
        status = "WARN" if res.warning else ("OK" if res.ok else "FAIL")
        lines.append(f"[{status}] {res.name}: {res.message}")
    return "\n".join(lines) if lines else "No checks executed."


def validate_env(strict: bool = False, env: Mapping[str, str] | None = None) -> tuple[bool, list[CheckResult]]:
    env_map = dict(env or os.environ)
    checks: list[CheckResult] = []

    def add(name: str, ok: bool, message: str, *, warning: bool = False) -> None:
        checks.append(CheckResult(name=name, ok=ok, message=message, warning=warning))

    db_url = env_map.get("DATABASE_URL")
    if not db_url:
        add("database_url", False, "DATABASE_URL is required")
    else:
        parsed = urlparse(db_url)
        ok = bool(parsed.scheme and (parsed.netloc or parsed.path))
        host = parsed.hostname or "<missing>"
        add(
            "database_url",
            ok,
            f"scheme={parsed.scheme or '<missing>'} host={host}",
        )

    openai_key = env_map.get("OPENAI_API_KEY")
    if not openai_key:
        add("openai_api_key", False, "OPENAI_API_KEY is required")
    else:
        valid = openai_key.startswith(("sk-", "sk-proj-"))
        add(
            "openai_api_key",
            valid,
            f"format={'valid' if valid else 'invalid'} ({_redact(openai_key)})",
        )

    auth_mode = (env_map.get("AUTH_MODE") or "auth0").strip().lower()
    if auth_mode == "demo":
        hashes = [h for h in (env_map.get("DEMO_TOKEN_SHA256_LIST") or "").split(",") if h.strip()]
        add(
            "demo_token_sha256_list",
            bool(hashes),
            "DEMO_TOKEN_SHA256_LIST must include at least one SHA256 digest when AUTH_MODE=demo.",
        )
    elif auth_mode != "dev":
        issuer = (env_map.get("AUTH0_ISSUER") or "").strip()
        domain = (env_map.get("AUTH0_DOMAIN") or "").strip()
        if issuer:
            normalized = issuer
            ok = normalized.startswith("https://") and normalized.endswith("/")
            add(
                "auth0_issuer",
                ok,
                "AUTH0_ISSUER must start with https:// and end with '/'",
            )
        elif domain:
            add("auth0_domain", True, f"AUTH0_DOMAIN={domain} (issuer will be derived)")
        else:
            add(
                "auth0_issuer",
                False,
                "Provide AUTH0_ISSUER (https://tenant/) or AUTH0_DOMAIN for auth0 mode.",
            )

        audience = (env_map.get("AUTH0_AUDIENCE") or "").strip()
        if audience:
            add(
                "auth0_audience",
                True,
                f"AUTH0_AUDIENCE configured (API Identifier) {_redact(audience, 6, 3)}",
            )
        else:
            add(
                "auth0_audience",
                False,
                (
                    "AUTH0_AUDIENCE missing. Set to your Auth0 API Identifier (expected 'aud' claim), "
                    "e.g. https://api.example.com or urn:my-api. Configure under Auth0 Dashboard → APIs → Identifier. "
                    "Provide AUTH0_ISSUER (https://tenant/) or AUTH0_DOMAIN so issuer can be derived."
                ),
            )

    app_env = (env_map.get("APP_ENV") or "dev").strip().lower()
    allow_prod_debug = env_map.get("ALLOW_PROD_DEBUG", "0")
    if app_env == "prod":
        add(
            "prod_debug_clamp",
            not _truthy(allow_prod_debug),
            "ALLOW_PROD_DEBUG must stay disabled (0) in prod",
        )
        if _truthy(env_map.get("ENABLE_RETRIEVAL_DEBUG", "0")):
            add(
                "prod_retrieval_debug_flag",
                True,
                "ENABLE_RETRIEVAL_DEBUG=1 in prod; ensure this is intentional",
                warning=True,
            )

    passed = all(check.ok for check in checks)
    warnings_present = any(check.warning for check in checks)
    overall = passed and (not strict or not warnings_present)
    return overall, checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate required environment variables.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    ok, results = validate_env(strict=args.strict)
    print(format_report(results))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
