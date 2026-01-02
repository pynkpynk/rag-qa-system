from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_run_token() -> str:
    # URL共有しても扱いやすい長さ
    return secrets.token_urlsafe(32)


def hash_run_token(token: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


def verify_run_token(token: str, expected_hash: str, secret: str) -> bool:
    actual = hash_run_token(token, secret)
    return hmac.compare_digest(actual, expected_hash)
