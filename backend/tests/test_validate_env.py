from scripts import validate_env as ve


BASE_ENV = {
    "DATABASE_URL": "postgresql://user:pass@localhost/db",
    "OPENAI_API_KEY": "sk-test-REDACTED",
    "AUTH_MODE": "auth0",
    "AUTH0_ISSUER": "https://tenant.example.com/",
    "AUTH0_AUDIENCE": "https://api.example.com",
    "APP_ENV": "dev",
}


def run_env(overrides: dict[str, str], strict: bool = False):
    env = BASE_ENV.copy()
    env.update(overrides)
    ok, checks = ve.validate_env(strict=strict, env=env)
    return ok, {c.name: c for c in checks}


def test_missing_database_url_fails():
    ok, checks = run_env({"DATABASE_URL": ""})
    assert not ok
    assert not checks["database_url"].ok


def test_bad_issuer_format_fails():
    ok, checks = run_env({"AUTH0_ISSUER": "http://tenant.example.com"})
    assert not ok
    assert not checks["auth0_issuer"].ok


def test_prod_debug_clamp_enforced():
    ok, checks = run_env({"APP_ENV": "prod", "ALLOW_PROD_DEBUG": "1"})
    assert not ok
    assert not checks["prod_debug_clamp"].ok


def test_prod_retrieval_debug_warning_strict_mode():
    ok, checks = run_env({"APP_ENV": "prod", "ALLOW_PROD_DEBUG": "0", "ENABLE_RETRIEVAL_DEBUG": "1"})
    assert ok, "warning should not fail without --strict"
    ok_strict, _ = run_env({"APP_ENV": "prod", "ALLOW_PROD_DEBUG": "0", "ENABLE_RETRIEVAL_DEBUG": "1"}, strict=True)
    assert not ok_strict, "strict mode should fail on warnings"


def test_redaction_of_openai_key():
    secret = "sk-test-REDACTED"
    ok, checks = run_env({"OPENAI_API_KEY": secret})
    assert ok
    message = checks["openai_api_key"].message
    assert "secretvalue0000" not in message


def test_missing_auth0_audience_has_hint():
    ok, checks = run_env({"AUTH0_AUDIENCE": ""})
    assert not ok
    message = checks["auth0_audience"].message
    assert "API Identifier" in message
    assert "Auth0 Dashboard" in message


def test_demo_mode_requires_hash_list():
    env = {
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "OPENAI_API_KEY": "sk-test-REDACTED",
        "AUTH_MODE": "demo",
        "APP_ENV": "prod",
        "DEMO_TOKEN_SHA256_LIST": "",
    }
    ok, check_list = ve.validate_env(env=env)
    checks = {c.name: c for c in check_list}
    assert not ok
    assert not checks["demo_token_sha256_list"].ok


def test_demo_mode_accepts_hashes():
    digest = "a" * 64
    env = {
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "OPENAI_API_KEY": "sk-test-REDACTED",
        "AUTH_MODE": "demo",
        "APP_ENV": "prod",
        "DEMO_TOKEN_SHA256_LIST": digest,
    }
    ok, check_list = ve.validate_env(env=env)
    checks = {c.name: c for c in check_list}
    assert ok
    assert checks["demo_token_sha256_list"].ok
