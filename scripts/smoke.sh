#!/usr/bin/env bash
set -euo pipefail

API_ORIGIN="${API_ORIGIN:-http://127.0.0.1:8000}"
API_BASE="${API_BASE:-${API_ORIGIN}/api}"
QUESTION="${QUESTION:-What is the P1 response time target for the Pro plan? Answer with citations.}"
K="${K:-6}"

die() { echo "ERROR: $*" >&2; exit 1; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"; }

curl_json() { curl -sS -f "$@"; }
json_pretty() { python -m json.tool; }

# ★ここが今回の核心：stdin が空にならない形で JSON を渡す
json_get() {
  # usage: json_get "<json>" "<key>"
  local json="$1"
  local key="$2"

  python -c '
import json, sys
key = sys.argv[1]
raw = sys.stdin.read()
if not raw.strip():
    print("json_parse_error: empty stdin", file=sys.stderr)
    sys.exit(2)
try:
    obj = json.loads(raw)
except Exception as e:
    print(f"json_parse_error: {e}", file=sys.stderr)
    sys.exit(2)
if not isinstance(obj, dict):
    print("json_not_object", file=sys.stderr)
    sys.exit(2)
val = obj.get(key, "")
print("" if val is None else val)
' "$key" <<<"$json"
}

abs_path() { python -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1"; }

require_cmd curl
require_cmd python

PDF_PATH="${1:-}"
[[ -n "$PDF_PATH" ]] || die "Usage: ./scripts/smoke.sh <pdf_path>"
PDF_ABS="$(abs_path "$PDF_PATH")"
[[ -f "$PDF_ABS" ]] || die "PDF not found: $PDF_ABS"

echo "API_BASE=$API_BASE"
echo "PDF=$PDF_ABS"
echo

echo "== Health =="
curl_json "${API_BASE}/health" | json_pretty
echo

echo "== List docs =="
DOCS_JSON="$(curl_json "${API_BASE}/docs")"
printf '%s\n' "$DOCS_JSON" | json_pretty
echo

echo "== Upload PDF ($PDF_ABS) =="
UPLOAD_JSON="$(curl_json -F "file=@${PDF_ABS}" "${API_BASE}/docs/upload")"
printf '%s\n' "$UPLOAD_JSON" | json_pretty
echo

DOC_ID="$(json_get "$UPLOAD_JSON" "document_id")"
[[ -n "$DOC_ID" ]] || die "Failed to read document_id from upload response"

echo "== Create run (attach doc) =="
RUN_PAYLOAD="$(python -c '
import json, sys
doc_id = sys.argv[1]
payload = {
  "config": {
    "model": "gpt-5-mini",
    "chunk": {"size": 800, "overlap": 120},
    "retriever": {"k": 8},
  },
  "document_ids": [doc_id],
}
print(json.dumps(payload))
' "$DOC_ID")"

RUN_JSON="$(curl_json -X POST "${API_BASE}/runs" -H "Content-Type: application/json" -d "$RUN_PAYLOAD")"
printf '%s\n' "$RUN_JSON" | json_pretty
echo

RUN_ID="$(json_get "$RUN_JSON" "run_id")"
[[ -n "$RUN_ID" ]] || die "Failed to read run_id from create run response"

echo "== Ask =="
ASK_PAYLOAD="$(python -c '
import json, sys
q = sys.argv[1]
k = int(sys.argv[2])
run_id = sys.argv[3]
print(json.dumps({"question": q, "k": k, "run_id": run_id}))
' "$QUESTION" "$K" "$RUN_ID")"

ASK_JSON="$(curl_json -X POST "${API_BASE}/chat/ask" -H "Content-Type: application/json" -d "$ASK_PAYLOAD")"
printf '%s\n' "$ASK_JSON" | json_pretty
echo

ANSWER_LEN="$(python -c '
import json, sys
j=json.loads(sys.stdin.read())
a=j.get("answer") or ""
print(len(a))
' <<<"$ASK_JSON")"
(( ANSWER_LEN > 0 )) || die "Ask returned empty answer"

echo "✅ Smoke OK"
echo "RUN_ID=$RUN_ID"
echo "DOC_ID=$DOC_ID"
