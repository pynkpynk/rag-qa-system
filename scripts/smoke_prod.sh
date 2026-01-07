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

retry_health() {
  local max_attempts=12
  local attempt=1
  local delay=1
  while true; do
    if run_request GET "${API_BASE%/}/api/health"; then
      return 0
    fi
    if [[ ${attempt} -ge ${max_attempts} ]]; then
      echo "[smoke] /api/health failed after ${max_attempts} attempts" >&2
      exit 1
    fi
    echo "[smoke] /api/health attempt ${attempt}/${max_attempts} failed, retrying in ${delay}s" >&2
    sleep "${delay}"
    attempt=$((attempt + 1))
    if [[ ${delay} -lt 10 ]]; then
      delay=$((delay + 1))
    fi
  done
}

run_request_expect_status() {
  local expected_status="$1"
  shift
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
  if [[ "${status}" != "${expected_status}" ]]; then
    echo "[smoke] ${method} ${url} expected status ${expected_status} but got ${status}" >&2
    if [[ -s "${body_file}" ]]; then
      cat "${body_file}" >&2
    else
      echo "(no body captured)" >&2
    fi
    exit 1
  fi
  if command -v jq >/dev/null 2>&1; then
    jq . "${body_file}" || cat "${body_file}"
  else
    cat "${body_file}"
  fi
}

echo "[smoke] 1/4 GET /api/health"
retry_health

echo "[smoke] 2/4 GET /api/chunks/health"
run_request GET "${API_BASE%/}/api/chunks/health" \
  -H "Authorization: Bearer ${TOKEN}"
chunks_health_body="${LAST_RESPONSE_BODY:-}"
if [[ -z "${chunks_health_body}" || ! -f "${chunks_health_body}" ]]; then
  echo "[smoke] missing /api/chunks/health body capture" >&2
  exit 1
fi
echo "[smoke] validating DB state from /api/chunks/health"
CHUNKS_HEALTH_BODY="${chunks_health_body}" SMOKE_ALLOW_ALEMBIC_BEHIND="${SMOKE_ALLOW_ALEMBIC_BEHIND:-0}" python - <<'PY'
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
head = db.get("alembic_head")
if not head:
    print("[smoke] FAIL: db.alembic_head missing or empty", file=sys.stderr)
    sys.exit(1)
is_head = db.get("is_alembic_head")
allow_env = (os.environ.get("SMOKE_ALLOW_ALEMBIC_BEHIND", "0") or "").lower()
allow = allow_env in {"1", "true", "yes", "on"}
if is_head is not True:
    msg = f"[smoke] DB revision {rev} != code head {head}"
    if allow:
        print(msg + " (allowed by SMOKE_ALLOW_ALEMBIC_BEHIND)", file=sys.stderr)
    else:
        print(msg + " (set SMOKE_ALLOW_ALEMBIC_BEHIND=1 to warn only)", file=sys.stderr)
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
def scan(obj, in_db_block=False):
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = key.lower()
            if lowered == "principal_sub":
                print("[smoke] FAIL: chunks health response leaked principal_sub", file=sys.stderr)
                sys.exit(1)
            if lowered.startswith("owner_sub"):
                print(f"[smoke] FAIL: chunks health response leaked {key}", file=sys.stderr)
                sys.exit(1)
            if lowered.startswith("db_") and not in_db_block:
                print(f"[smoke] FAIL: chunks health response leaked {key}", file=sys.stderr)
                sys.exit(1)
            scan(value, in_db_block or lowered == "db")
    elif isinstance(obj, list):
        for item in obj:
            scan(item, in_db_block)

scan(payload, False)
PY

echo "[smoke] 3/4 POST /api/search"
run_request POST "${API_BASE%/}/api/search" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"q":"example","mode":"library","limit":5,"debug":true}'
search_body="${LAST_RESPONSE_BODY:-}"
if [[ -z "${search_body}" || ! -f "${search_body}" ]]; then
  echo "[smoke] missing /api/search body capture" >&2
  exit 1
fi
SEARCH_BODY="${search_body}" python - <<'PY'
import json
import os
import sys

body_path = os.environ.get("SEARCH_BODY")
if not body_path or not os.path.exists(body_path):
    print("[smoke] FAIL: search body missing", file=sys.stderr)
    sys.exit(1)
with open(body_path, "r", encoding="utf-8") as f:
    payload = json.load(f)
debug = payload.get("debug") or {}
mode = debug.get("used_mode")
reason = debug.get("doc_filter_reason")
if not mode:
    print("[smoke] FAIL: debug.used_mode missing", file=sys.stderr)
    sys.exit(1)
if mode != "library":
    print(f"[smoke] FAIL: debug.used_mode {mode!r} != 'library'", file=sys.stderr)
    sys.exit(1)
if not reason:
    print("[smoke] FAIL: debug.doc_filter_reason missing", file=sys.stderr)
    sys.exit(1)
if reason != "mode=library":
    print(f"[smoke] FAIL: debug.doc_filter_reason {reason!r} != 'mode=library'", file=sys.stderr)
    sys.exit(1)
banned = {"db_host", "db_name", "db_port", "principal_sub", "owner_sub_used", "owner_sub_alt"}
leaks = [k for k in banned if k in debug]
if leaks:
    print(f"[smoke] FAIL: debug payload leaks sensitive keys {leaks}", file=sys.stderr)
    sys.exit(1)
PY

echo "[smoke] validating selected_docs 422 behavior"
run_request_expect_status 422 POST "${API_BASE%/}/api/search" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"q":"example","mode":"selected_docs","debug":true}'
invalid_body="${LAST_RESPONSE_BODY:-}"
if [[ -z "${invalid_body}" || ! -f "${invalid_body}" ]]; then
  echo "[smoke] missing selected_docs error body" >&2
  exit 1
fi
INVALID_BODY="${invalid_body}" python - <<'PY'
import json
import os
import sys

body_path = os.environ.get("INVALID_BODY")
if not body_path or not os.path.exists(body_path):
    print("[smoke] FAIL: selected_docs error body missing", file=sys.stderr)
    sys.exit(1)
with open(body_path, "r", encoding="utf-8") as f:
    payload = json.load(f)
error = payload.get("error") or {}
message = error.get("message") or ""
expected = "document_ids is required when mode=selected_docs"
if expected not in message:
    print(f"[smoke] FAIL: expected error message containing {expected!r}, got {message!r}", file=sys.stderr)
    sys.exit(1)
PY

echo "[smoke] validating selected_docs success path"
select_doc_id() {
  if [[ -n "${SMOKE_DOC_ID:-}" ]]; then
    echo "[smoke] using SMOKE_DOC_ID=${SMOKE_DOC_ID}" >&2
    echo "${SMOKE_DOC_ID}"
    return 0
  fi
  run_request GET "${API_BASE%/}/api/docs" -H "Authorization: Bearer ${TOKEN}" >/dev/null
  docs_body="${LAST_RESPONSE_BODY:-}"
  if [[ -z "${docs_body}" || ! -f "${docs_body}" ]]; then
    echo "[smoke] missing docs body capture" >&2
    return 1
  fi
  doc_id="$(DOCS_BODY="${docs_body}" python - <<'PY'
import json
import os
body_path = os.environ.get("DOCS_BODY")
if not body_path or not os.path.exists(body_path):
    raise SystemExit("DOCS_BODY missing or does not point to a file")
with open(body_path, "r", encoding="utf-8") as f:
    docs = json.load(f)
if not isinstance(docs, list) or not docs:
    raise SystemExit()
doc_id = docs[0].get("document_id")
if not doc_id:
    raise SystemExit()
print(doc_id)
PY
)"
  if [[ -n "${doc_id}" ]]; then
    echo "${doc_id}"
    return 0
  fi
  return 1
}

ensure_doc_id() {
  local doc_id
  doc_id="$(select_doc_id || true)"
  if [[ -n "${doc_id}" ]]; then
    echo "${doc_id}"
    return 0
  fi
  if [[ "${SMOKE_UPLOAD_FIXTURE:-0}" == "1" ]]; then
    echo "[smoke] uploading ragqa_smoke.pdf for selected_docs validation" >&2
    run_request POST "${API_BASE%/}/api/docs/upload" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: multipart/form-data" \
      -F "file=@${repo_root}/backend/tests/fixtures/ragqa_smoke.pdf" >/dev/null
    upload_body="${LAST_RESPONSE_BODY:-}"
    doc_id="$(UPLOAD_BODY="${upload_body}" python - <<'PY'
import json
import os
body_path = os.environ.get("UPLOAD_BODY")
if not body_path or not os.path.exists(body_path):
    raise SystemExit("UPLOAD_BODY missing")
with open(body_path, "r", encoding="utf-8") as f:
    payload = json.load(f)
doc_id = payload.get("document_id")
if not doc_id:
    raise SystemExit()
print(doc_id)
PY
)"
    if [[ -n "${doc_id}" ]]; then
      echo "${doc_id}"
      return 0
    fi
    echo "[smoke] upload failed to produce a document_id" >&2
  fi
  if [[ "${STRICT_SMOKE:-0}" == "1" ]]; then
    echo "[smoke] FAIL: no documents available for selected_docs checks" >&2
    exit 1
  else
    echo "[smoke] SKIP selected_docs checks: no documents available" >&2
    echo ""
    return 0
  fi
}

selected_doc_id="$(ensure_doc_id)"
selected_doc_id="${selected_doc_id//$'\r'/}"
selected_doc_id="${selected_doc_id//$'\n'/}"
selected_doc_id="${selected_doc_id:-}"
if [[ -z "${selected_doc_id}" ]]; then
  selected_doc_id=""
fi
if [[ -z "${selected_doc_id}" ]]; then
  echo "[smoke] skipping selected_docs validation due to missing doc_id" >&2
  if [[ "${STRICT_SMOKE:-0}" == "1" ]]; then
    exit 1
  fi
else
  echo "[smoke] validating selected_docs success path"
  run_request POST "${API_BASE%/}/api/search" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data '{"q":"example","mode":"selected_docs","document_ids":["'"${selected_doc_id}"'"],"debug":true}'
  selected_search_body="${LAST_RESPONSE_BODY:-}"
  if [[ -z "${selected_search_body}" || ! -f "${selected_search_body}" ]]; then
    echo "[smoke] missing selected_docs search body" >&2
    exit 1
  fi
  SELECTED_SEARCH_BODY="${selected_search_body}" SELECTED_DOC_ID="${selected_doc_id}" python - <<'PY'
import json
import os
import sys

body_path = os.environ.get("SELECTED_SEARCH_BODY")
doc_id = os.environ.get("SELECTED_DOC_ID")
if not body_path or not os.path.exists(body_path):
    print("[smoke] FAIL: selected_docs search body missing", file=sys.stderr)
    sys.exit(1)
with open(body_path, "r", encoding="utf-8") as f:
    payload = json.load(f)
debug = payload.get("debug") or {}
mode = debug.get("used_mode")
reason = debug.get("doc_filter_reason")
if mode != "selected_docs":
    print(f"[smoke] FAIL: debug.used_mode {mode!r} != 'selected_docs'", file=sys.stderr)
    sys.exit(1)
if reason != "mode=selected_docs":
    print(f"[smoke] FAIL: debug.doc_filter_reason {reason!r} != 'mode=selected_docs'", file=sys.stderr)
    sys.exit(1)
used_filter = debug.get("used_use_doc_filter")
if used_filter is not True:
    print(f"[smoke] FAIL: debug.used_use_doc_filter {used_filter!r} != True", file=sys.stderr)
    sys.exit(1)
hits = payload.get("hits") or []
for hit in hits:
    if hit.get("document_id") != doc_id:
        print(f"[smoke] FAIL: hit document_id {hit.get('document_id')!r} != expected {doc_id!r}", file=sys.stderr)
        sys.exit(1)
banned = {"db_host", "db_name", "db_port", "principal_sub", "owner_sub_used", "owner_sub_alt"}
leaks = [k for k in banned if k in debug]
if leaks:
    print(f"[smoke] FAIL: debug payload leaks sensitive keys {leaks}", file=sys.stderr)
    sys.exit(1)
PY
fi
run_request POST "${API_BASE%/}/api/search" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"q":"example","mode":"selected_docs","document_ids":["'"${selected_doc_id}"'"],"debug":true}'
selected_search_body="${LAST_RESPONSE_BODY:-}"
if [[ -z "${selected_search_body}" || ! -f "${selected_search_body}" ]]; then
  echo "[smoke] missing selected_docs search body" >&2
  exit 1
fi
SELECTED_SEARCH_BODY="${selected_search_body}" SELECTED_DOC_ID="${selected_doc_id}" python - <<'PY'
import json
import os
import sys

body_path = os.environ.get("SELECTED_SEARCH_BODY")
doc_id = os.environ.get("SELECTED_DOC_ID")
if not body_path or not os.path.exists(body_path):
    print("[smoke] FAIL: selected_docs search body missing", file=sys.stderr)
    sys.exit(1)
with open(body_path, "r", encoding="utf-8") as f:
    payload = json.load(f)
debug = payload.get("debug") or {}
mode = debug.get("used_mode")
reason = debug.get("doc_filter_reason")
if mode != "selected_docs":
    print(f"[smoke] FAIL: debug.used_mode {mode!r} != 'selected_docs'", file=sys.stderr)
    sys.exit(1)
if reason != "mode=selected_docs":
    print(f"[smoke] FAIL: debug.doc_filter_reason {reason!r} != 'mode=selected_docs'", file=sys.stderr)
    sys.exit(1)
used_filter = debug.get("used_use_doc_filter")
if used_filter is not True:
    print(f"[smoke] FAIL: debug.used_use_doc_filter {used_filter!r} != True", file=sys.stderr)
    sys.exit(1)
banned = {"db_host", "db_name", "db_port", "principal_sub", "owner_sub_used", "owner_sub_alt"}
leaks = [k for k in banned if k in debug]
if leaks:
    print(f"[smoke] FAIL: debug payload leaks sensitive keys {leaks}", file=sys.stderr)
    sys.exit(1)
hits = payload.get("hits") or []
for hit in hits:
    if hit.get("document_id") != doc_id:
        print(f"[smoke] FAIL: hit document_id {hit.get('document_id')!r} != expected {doc_id!r}", file=sys.stderr)
        sys.exit(1)
PY

echo "[smoke] OK"
