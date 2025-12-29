#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEV_UP_SCRIPT="${SCRIPT_DIR}/dev_up.sh"
DEV_DOWN_SCRIPT="${SCRIPT_DIR}/dev_down.sh"

log() { printf '[smoke] %s\n' "$*"; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }; }
require_cmd curl

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
APP_ENV=${APP_ENV:-dev}
ALLOW_PROD_DEBUG=${ALLOW_PROD_DEBUG:-1}
MAX_REQUEST_BYTES=${MAX_REQUEST_BYTES:-}
RATE_LIMIT_ENABLED=${RATE_LIMIT_ENABLED:-0}
RUN_ID=${RUN_ID:-}
SMOKE_MAX_REQUEST_BYTES=${SMOKE_MAX_REQUEST_BYTES:-1024}
SMOKE_FORCE_RESTART=${SMOKE_FORCE_RESTART:-0}
if [ -z "$MAX_REQUEST_BYTES" ]; then
  MAX_REQUEST_BYTES=$SMOKE_MAX_REQUEST_BYTES
  log "MAX_REQUEST_BYTES not provided; defaulting to ${MAX_REQUEST_BYTES}"
fi
export MAX_REQUEST_BYTES RATE_LIMIT_ENABLED APP_ENV ALLOW_PROD_DEBUG
TMP_DIR=$(mktemp -d)
SERVER_STARTED=0
cleanup() {
  rm -rf "$TMP_DIR"
  if [ "$SERVER_STARTED" -eq 1 ] && [ -x "$DEV_DOWN_SCRIPT" ]; then
    ( bash "$DEV_DOWN_SCRIPT" >/dev/null 2>&1 || true )
  fi
}
trap cleanup EXIT
JQ_AVAILABLE=0
if command -v jq >/dev/null 2>&1; then JQ_AVAILABLE=1; fi

json_field_present() {
  local field=$1 file=$2
  if [ "$JQ_AVAILABLE" -eq 1 ]; then
    jq -e ".${field} != null" "$file" >/dev/null 2>&1
  else
    grep -q "\"${field}\"" "$file"
  fi
}

json_field_absent() {
  local field=$1 file=$2
  if [ "$JQ_AVAILABLE" -eq 1 ]; then
    jq -e ".${field} == null" "$file" >/dev/null 2>&1
  else
    ! grep -q "\"${field}\"" "$file"
  fi
}

health_check() {
  log "Checking /api/health at ${BASE_URL}"
  code=$(curl -s -o "$TMP_DIR/health.json" -w '%{http_code}' "${BASE_URL}/api/health")
  if [ "$code" != "200" ]; then
    echo "Health check failed: HTTP ${code}" >&2
    cat "$TMP_DIR/health.json" >&2
    exit 1
  fi
  log "Health check OK"
}

chat_smoke() {
  if [ -z "$RUN_ID" ]; then
    log "RUN_ID not set; skipping /api/chat/ask smoke"
    return
  fi
  log "POST /api/chat/ask (RUN_ID=${RUN_ID})"
  payload='{"question":"Smoke RC test","run_id":"'"$RUN_ID"'","debug":true}'
  code=$(curl -s -o "$TMP_DIR/chat.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "${BASE_URL}/api/chat/ask")
  if [ "$code" != "200" ]; then
    echo "chat.ask smoke failed: HTTP ${code}" >&2
    cat "$TMP_DIR/chat.json" >&2
    exit 1
  fi
  if [ "$APP_ENV" = "prod" ] && [ "${ALLOW_PROD_DEBUG}" = "0" ]; then
    if ! json_field_absent "retrieval_debug" "$TMP_DIR/chat.json"; then
      echo "Prod clamp violated: retrieval_debug present" >&2
      exit 1
    fi
    if ! json_field_absent "debug_meta" "$TMP_DIR/chat.json"; then
      echo "Prod clamp violated: debug_meta present" >&2
      exit 1
    fi
    log "Prod clamp behavior confirmed"
  else
    log "chat.ask succeeded (dev/stage); inspect $TMP_DIR/chat.json if needed"
  fi
}

body_size_check() {
  local target_run_id="${RUN_ID:-SMOKE-DUMMY-RUN}"
  log "Triggering body size limit (MAX_REQUEST_BYTES=${MAX_REQUEST_BYTES})"
  local over=$((MAX_REQUEST_BYTES + 1024))
  if [ "$over" -le 0 ]; then over=2048; fi
  local filler
  filler=$(make_ascii_payload "$over")
  local payload_file="$TMP_DIR/body_payload.json"
  printf '{"question":"%s","run_id":"%s"}' "$filler" "$target_run_id" > "$payload_file"
  local target_endpoint="${BASE_URL}/api/_smoke/echo"
  local smoke_endpoint_enabled=1
  if ! curl -s -o /dev/null "$target_endpoint" >/dev/null 2>&1; then
    smoke_endpoint_enabled=0
    target_endpoint="${BASE_URL}/api/chat/ask"
  fi
  code=$(curl -s -o "$TMP_DIR/body.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data "@${payload_file}" \
    "$target_endpoint" || true)
  if [ "$smoke_endpoint_enabled" -eq 1 ] && [ "$code" = "404" ]; then
    echo "Smoke endpoint is disabled on the running server (404)." >&2
    echo "Start dev_up with ENABLE_SMOKE_ENDPOINT=1 (and APP_ENV=dev) or let smoke.sh manage the server." >&2
    exit 1
  fi
  if [ "$code" != "413" ]; then
    echo "Expected 413 but got ${code}" >&2
    head -c 400 "$TMP_DIR/body.json" >&2 || true
    echo >&2 "Hint: ensure server started with MAX_REQUEST_BYTES=${MAX_REQUEST_BYTES} (use dev_up.sh)."
    exit 1
  fi
  log "Body size limit confirmed"
}

make_ascii_payload() {
  local size=$1
  if [ "$size" -le 0 ]; then size=128; fi
  LC_ALL=C head -c "$size" </dev/zero | LC_ALL=C tr '\0' 'X'
}

rate_limit_check() {
  if [ "$RATE_LIMIT_ENABLED" != "1" ]; then
    log "Rate limit disabled; skipping 429 test"
    return
  fi
  if [ -z "$RUN_ID" ]; then
    log "RUN_ID not set; skipping rate limit test"
    return
  fi
  log "Checking rate limiter"
  payload='{"question":"Rate limit","run_id":"'"$RUN_ID"'"}'
  for i in 1 2; do
    curl -s -o /dev/null -w '' \
      -H 'Content-Type: application/json' \
      -d "$payload" "${BASE_URL}/api/chat/ask" >/dev/null
  done
  code=$(curl -s -o "$TMP_DIR/rl.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d "$payload" "${BASE_URL}/api/chat/ask" || true)
  if [ "$code" != "429" ]; then
    echo "Expected 429 after rate limit but got ${code}" >&2
    cat "$TMP_DIR/rl.json" >&2
    exit 1
  fi
  log "Rate limiter responded with 429 as expected"
}

maybe_start_server() {
  case "$BASE_URL" in
    http://127.0.0.1:*|http://localhost:*|http://0.0.0.0:*)
      local healthy=1
      curl -s --max-time 1 "${BASE_URL}/api/health" >/dev/null 2>&1 || healthy=0
      if [ "$healthy" -eq 1 ] && [ "$SMOKE_FORCE_RESTART" != "1" ]; then
        log "Local server already healthy; not restarting"
        return
      fi
      if [ -x "$DEV_DOWN_SCRIPT" ]; then bash "$DEV_DOWN_SCRIPT" >/dev/null 2>&1 || true; fi
      if [ -x "$DEV_UP_SCRIPT" ]; then
        SERVER_STARTED=1
        log "Starting local dev server via dev_up.sh (MAX_REQUEST_BYTES=${MAX_REQUEST_BYTES}, DEV_RELOAD=0)"
        ENABLE_SMOKE_ENDPOINT=1 DEV_RELOAD=0 bash "$DEV_UP_SCRIPT"
      else
        log "dev_up.sh not found; assuming server already running"
      fi
      ;;
    *)
      log "BASE_URL is remote; not managing local server"
      ;;
  esac
}

maybe_start_server
health_check
chat_smoke
body_size_check
rate_limit_check

log "Smoke checks completed"
