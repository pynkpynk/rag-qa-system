#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE:-}" ]]; then
  echo "API_BASE env var is required" >&2
  exit 1
fi
if [[ -z "${TOKEN:-}" ]]; then
  echo "TOKEN env var is required" >&2
  exit 1
fi

token_prefix="${TOKEN:0:8}"
echo "[smoke] API_BASE=${API_BASE} token_prefix=${token_prefix}"

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d)"
LAST_RESPONSE_BODY=""
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

run_request() {
  local method="$1"
  local url="$2"
  shift 2
  local body_file
  body_file="$(mktemp "${tmpdir}/body.XXXXXX")"
  local status
  set +e
  status=$(
    curl -sS -o "${body_file}" -w "%{http_code}" \
      "$@" \
      -X "${method}" \
      "${url}"
  )
  local curl_rc=$?
  set -e
  LAST_RESPONSE_BODY="${body_file}"
  if [[ ${curl_rc} -ne 0 ]]; then
    echo "[smoke] curl error rc=${curl_rc} (${method} ${url})" >&2
    if [[ -s "${body_file}" ]]; then
      cat "${body_file}" >&2
    else
      echo "(no body captured)" >&2
    fi
    exit 1
  fi
  if [[ ${status} =~ ^2 ]]; then
    if command -v jq >/dev/null 2>&1; then
      jq . "${body_file}" || cat "${body_file}"
    else
      cat "${body_file}"
    fi
    return 0
  fi
  echo "[smoke] ${method} ${url} failed (status ${status})" >&2
  if [[ -s "${body_file}" ]]; then
    cat "${body_file}" >&2
  else
    echo "(no body captured)" >&2
  fi
  exit 1
}

echo "[smoke] 1/3 GET /api/health"
run_request GET "${API_BASE%/}/api/health"

echo "[smoke] 2/3 GET /api/chunks/health"
run_request GET "${API_BASE%/}/api/chunks/health" \
  -H "Authorization: Bearer ${TOKEN}"
chunks_health_body="${LAST_RESPONSE_BODY:-}"
if [[ -z "${chunks_health_body}" || ! -f "${chunks_health_body}" ]]; then
  echo "[smoke] missing /api/chunks/health body capture" >&2
  exit 1
fi
echo "[smoke] validating DB state from /api/chunks/health"
CHUNKS_HEALTH_BODY="${chunks_health_body}" python - <<'PY'
import json
import os
import sys

body_path = os.environ.get("CHUNKS_HEALTH_BODY")
if not body_path or not os.path.exists(body_path):
    print("[smoke] FAIL: chunks health body missing", file=sys.stderr)
    sys.exit(1)

with open(body_path, "r", encoding="utf-8") as f:
    payload = json.load(f)

db = payload.get("db") or {}
rev = db.get("alembic_revision")
if not rev:
    print("[smoke] FAIL: db.alembic_revision missing or empty", file=sys.stderr)
    sys.exit(1)

dialect = (db.get("dialect") or "").lower()
if dialect == "postgresql":
    if db.get("chunks_fts_column") is not True:
        print("[smoke] FAIL: chunks_fts_column not reported as present", file=sys.stderr)
        sys.exit(1)
    if db.get("pg_trgm_installed") is not True:
        print("[smoke] FAIL: pg_trgm extension not reported", file=sys.stderr)
        sys.exit(1)
    if db.get("fts_gin_index") is not True:
        print("[smoke] warning: fts_gin_index not reported as present", file=sys.stderr)
    if db.get("text_trgm_index") is not True:
        print("[smoke] warning: text_trgm_index not reported as present", file=sys.stderr)
else:
    print(f"[smoke] db dialect={dialect or 'unknown'} (no pg-specific enforcement)")
PY

echo "[smoke] 3/3 POST /api/search"
run_request POST "${API_BASE%/}/api/search" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"q":"example","mode":"library","limit":5,"debug":true}'

echo "[smoke] OK"
