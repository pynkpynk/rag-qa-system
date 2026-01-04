#!/usr/bin/env bash
set -euo pipefail

for var in API_BASE TOKEN_A TOKEN_B PDF; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required env var: $var" >&2
    exit 1
  fi
done

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

log() {
  echo "[$(date -u +"%H:%M:%S")] $*"
}

api_call() {
  local method="$1"
  local url="$2"
  shift 2
  HTTP_STATUS=$(curl -sS -o "$tmp_dir/body.json" -w "%{http_code}" -X "$method" "$url" "$@")
  BODY="$(cat "$tmp_dir/body.json")"
}

fail() {
  log "FAIL: $*"
  exit 1
}

pass() {
  log "PASS: $*"
}

upload_doc() {
  local token="$1"
  api_call POST "$API_BASE/docs/upload" \
    -H "Authorization: Bearer $token" \
    -F "file=@${PDF};type=application/pdf"
  if [[ "$HTTP_STATUS" != "200" ]]; then
    fail "Upload failed ($HTTP_STATUS): $BODY"
  fi
  echo "$BODY" | jq -r '.document_id'
}

list_docs() {
  local token="$1"
  api_call GET "$API_BASE/docs" -H "Authorization: Bearer $token"
  if [[ "$HTTP_STATUS" != "200" ]]; then
    fail "List docs failed for token ($HTTP_STATUS): $BODY"
  fi
  echo "$BODY" | jq -r '.[].document_id'
}

ask_doc() {
  local token="$1"
  local doc_id="$2"
  api_call POST "$API_BASE/chat/ask" \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"Smoke test question\",\"document_ids\":[\"$doc_id\"],\"k\":3}"
  if [[ "$HTTP_STATUS" != "200" ]]; then
    fail "Ask failed ($HTTP_STATUS): $BODY"
  fi
  echo "$BODY"
}

fetch_chunk() {
  local token="$1"
  local chunk_id="$2"
  api_call GET "$API_BASE/chunks/$chunk_id" -H "Authorization: Bearer $token"
  echo "$HTTP_STATUS"
}

create_run() {
  local token="$1"
  local doc_id="$2"
  api_call POST "$API_BASE/runs" \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -d "{\"config\":{\"label\":\"smoke\"},\"document_ids\":[\"$doc_id\"]}"
  if [[ "$HTTP_STATUS" != "200" ]]; then
    fail "Create run failed ($HTTP_STATUS): $BODY"
  fi
  echo "$BODY" | jq -r '.run_id'
}

get_run_as() {
  local token="$1"
  local run_id="$2"
  api_call GET "$API_BASE/runs/$run_id" -H "Authorization: Bearer $token"
  echo "$HTTP_STATUS"
}

log "Uploading PDF as TOKEN_A"
doc_id="$(upload_doc "$TOKEN_A")"
pass "Uploaded doc_id=$doc_id"

log "Verifying visibility"
docs_a="$(list_docs "$TOKEN_A")"
echo "$docs_a" | grep -q "$doc_id" || fail "Doc not visible to owner"
docs_b="$(list_docs "$TOKEN_B")"
if echo "$docs_b" | grep -q "$doc_id"; then
  fail "Doc unexpectedly visible to TOKEN_B"
fi
pass "Document visible only to owner"

log "Running ask as TOKEN_A"
ask_resp="$(ask_doc "$TOKEN_A" "$doc_id")"
chunk_id="$(echo "$ask_resp" | jq -r '.citations[0].chunk_id')"
if [[ -z "$chunk_id" || "$chunk_id" == "null" ]]; then
  fail "Ask response missing chunk_id"
fi
pass "Ask succeeded with chunk $chunk_id"

log "Checking chunk access"
status_a="$(fetch_chunk "$TOKEN_A" "$chunk_id")"
[[ "$status_a" == "200" ]] || fail "Owner chunk fetch failed ($status_a)"
status_b="$(fetch_chunk "$TOKEN_B" "$chunk_id")"
if [[ "$status_b" == "200" ]]; then
  fail "Chunk accessible to TOKEN_B"
fi
pass "Chunk isolation confirmed"

log "Creating run for TOKEN_A"
run_id="$(create_run "$TOKEN_A" "$doc_id")"
pass "Run created: $run_id"

log "Ensuring TOKEN_B cannot read run"
status_run_b="$(get_run_as "$TOKEN_B" "$run_id")"
if [[ "$status_run_b" == "200" ]]; then
  fail "Run visible to TOKEN_B"
fi
pass "Run isolation confirmed"

log "Smoke test complete"
