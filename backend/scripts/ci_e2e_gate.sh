#!/usr/bin/env bash
set -euo pipefail

KEEP_SERVER="${KEEP_SERVER:-0}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ci-e2e] Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd curl
require_cmd jq
require_cmd lsof

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_FILE="${BACKEND_DIR}/.ci_e2e_server.log"
DB_CONTAINER="${RAGQA_CI_DB_CONTAINER:-ragqa-ci-pg}"
DB_PORT="${RAGQA_CI_DB_PORT:-${DB_PORT:-55432}}"

API_HOST="127.0.0.1"
API_PORT="${RAGQA_CI_API_PORT:-${API_PORT:-8010}}"
API_BASE="http://${API_HOST}:${API_PORT}/api"

TMP_DIR="$(mktemp -d)"
TMP_HEADERS="${TMP_DIR}/headers"
TMP_BODY="${TMP_DIR}/body"

LAST_REQUEST_ID="n/a"
REMOVE_CONTAINER=0
SERVER_PID=""

cleanup() {
  local code=$?

  if [[ "${KEEP_SERVER}" == "1" ]]; then
    echo "[ci-e2e] KEEP_SERVER=1 -> skip cleanup (server/container stay alive)"
    echo "[ci-e2e] log: ${LOG_FILE}"
    echo "[ci-e2e] tmp: ${TMP_DIR}"
    exit "${code}"
  fi

  if [[ -n "${SERVER_PID}" ]] && ps -p "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi

  if [[ "${REMOVE_CONTAINER}" == "1" ]]; then
    docker rm -f "${DB_CONTAINER}" >/dev/null 2>&1 || true
  fi

  rm -rf "${TMP_DIR}"
  exit "${code}"
}
trap cleanup EXIT

abort() {
  echo "[ci-e2e] $*" >&2
  echo "[ci-e2e] Last request id: ${LAST_REQUEST_ID}" >&2
  echo "[ci-e2e] log file: ${LOG_FILE}" >&2
  echo "[ci-e2e] tmp dir: ${TMP_DIR}" >&2

  if [[ -f "${TMP_BODY}" ]]; then
    echo "[ci-e2e] Last response body:" >&2
    cat "${TMP_BODY}" >&2 || true
  fi

  if [[ -f "${LOG_FILE}" ]]; then
    echo "[ci-e2e] ---- server log tail ----" >&2
    tail -n 300 "${LOG_FILE}" >&2 || true
  fi

  exit 1
}

port_must_be_free() {
  local port="$1"
  local label="$2"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[ci-e2e] ${label} port ${port} already in use" >&2
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >&2 || true
    exit 1
  fi
}

port_must_be_free "${API_PORT}" "API"
port_must_be_free "${DB_PORT}" "DB"

echo "[ci-e2e] Starting pgvector container ${DB_CONTAINER}"
if docker ps -a --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
  docker rm -f "${DB_CONTAINER}" >/dev/null 2>&1 || true
fi

docker run -d \
  --name "${DB_CONTAINER}" \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=postgres \
  -p "${DB_PORT}:5432" \
  pgvector/pgvector:pg17 >/dev/null
REMOVE_CONTAINER=1

echo "[ci-e2e] Waiting for Postgres"
for _ in {1..60}; do
  if docker exec "${DB_CONTAINER}" pg_isready -U postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done || abort "Postgres did not become ready"

docker exec "${DB_CONTAINER}" psql -U postgres -c "CREATE DATABASE ragqa_ci;" >/dev/null 2>&1 || true
docker exec "${DB_CONTAINER}" psql -U postgres -d ragqa_ci -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
docker exec "${DB_CONTAINER}" psql -U postgres -d ragqa_ci -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" >/dev/null
TRGM_AVAILABLE_DB=$(docker exec "${DB_CONTAINER}" psql -U postgres -d ragqa_ci -Atc "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_trgm');" 2>/dev/null | tr -d '[:space:]')
if [[ "${TRGM_AVAILABLE_DB}" != "t" && "${TRGM_AVAILABLE_DB}" != "true" && "${TRGM_AVAILABLE_DB}" != "1" ]]; then
  abort "pg_trgm extension not installed in ragqa_ci database"
fi

export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:${DB_PORT}/ragqa_ci"
export OPENAI_OFFLINE="${OPENAI_OFFLINE:-1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-ci-dummy}"
export CORS_ORIGIN="${CORS_ORIGIN:-http://localhost:5173}"
export AUTH_MODE="dev"
export DEV_SUB="${DEV_SUB:-ci-user}"
export ADMIN_SUBS="${ADMIN_SUBS:-ci-user}"
export ALLOW_PROD_DEBUG="${ALLOW_PROD_DEBUG:-1}"
export ENABLE_RETRIEVAL_DEBUG="1"
export RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH="${RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH:-0}"
export ENABLE_HYBRID="1"
export ENABLE_TRGM="1"

cd "${BACKEND_DIR}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${BACKEND_DIR}/../.venv/bin/python" ]]; then
    PYTHON_BIN="${BACKEND_DIR}/../.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi

echo "[ci-e2e] Running alembic upgrade"
if [[ -f "${BACKEND_DIR}/alembic.ini" ]]; then
  "${PYTHON_BIN}" -m alembic -c alembic.ini upgrade head >/dev/null
else
  "${PYTHON_BIN}" -m alembic upgrade head >/dev/null
fi

echo "[ci-e2e] Starting uvicorn on port ${API_PORT}"
touch "${LOG_FILE}"
: > "${LOG_FILE}"
"${PYTHON_BIN}" -m uvicorn app.main:app --host "${API_HOST}" --port "${API_PORT}" >>"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

echo "[ci-e2e] Waiting for API health"
for _ in {1..60}; do
  if curl -sSf "http://${API_HOST}:${API_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done || abort "API health check failed"

call_api() {
  local method="$1"
  local path="$2"
  shift 2

  local req_id="ci-e2e-$(date +%s%N)"
  local status

  if ! status=$(
    curl -sS -D "${TMP_HEADERS}" -o "${TMP_BODY}" -w "%{http_code}" \
      -H "Authorization: Bearer dev-token" \
      -H "x-dev-sub: ${DEV_SUB}" \
      -H "X-Request-ID: ${req_id}" \
      "$@" \
      -X "${method}" "${API_BASE}${path}"
  ); then
    LAST_REQUEST_ID="${req_id}"
    abort "curl failed for ${method} ${path}"
  fi

  LAST_REQUEST_ID="$(grep -i '^x-request-id:' "${TMP_HEADERS}" | tail -n1 | awk '{print $2}' | tr -d '\r')"
  if [[ -z "${LAST_REQUEST_ID}" ]]; then
    LAST_REQUEST_ID="${req_id}"
  fi

  RESPONSE_STATUS="${status}"
}

call_json() {
  local method="$1"
  local path="$2"
  local body="$3"
  call_api "${method}" "${path}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    --data "${body}"
}

PDF_PATH="${TMP_DIR}/ragqa_ci_test.pdf"
echo "[ci-e2e] Generating test PDF: ${PDF_PATH}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/make_test_pdf.py" "${PDF_PATH}" >/dev/null

echo "[ci-e2e] Uploading PDF"
call_api "POST" "/docs/upload" -H "Accept: application/json" -F "file=@${PDF_PATH};type=application/pdf"
[[ "${RESPONSE_STATUS}" == "200" ]] || abort "Upload failed (${RESPONSE_STATUS})"

DOC_ID="$(jq -r '.document_id' "${TMP_BODY}")"
[[ -n "${DOC_ID}" && "${DOC_ID}" != "null" ]] || abort "document_id missing"

echo "[ci-e2e] Waiting for indexing..."
DOC_STATUS=""
for _ in {1..60}; do
  call_api "GET" "/docs/${DOC_ID}" -H "Accept: application/json"
  [[ "${RESPONSE_STATUS}" == "200" ]] || abort "Fetching doc status failed (${RESPONSE_STATUS})"
  DOC_STATUS="$(jq -r '.status' "${TMP_BODY}")"
  if [[ "${DOC_STATUS}" == "indexed" ]]; then
    break
  fi
  if [[ "${DOC_STATUS}" == "failed" ]]; then
    ERR_MSG="$(jq -r '.error' "${TMP_BODY}")"
    abort "Document indexing failed: ${ERR_MSG}"
  fi
  sleep 1
done
[[ "${DOC_STATUS}" == "indexed" ]] || abort "Document never reached indexed status"

echo "[ci-e2e] Sanity check: chunks exist?"
CHUNKS_TOTAL="$(docker exec "${DB_CONTAINER}" psql -U postgres -d ragqa_ci -Atc "SELECT count(*) FROM chunks;" 2>/dev/null | tr -d '[:space:]' || true)"
if [[ -z "${CHUNKS_TOTAL}" ]]; then
  abort "Could not query chunks count (schema/connection issue)"
fi
if [[ "${CHUNKS_TOTAL}" == "0" ]]; then
  abort "No chunks were indexed (likely test PDF has no extractable text)"
fi

echo "[ci-e2e] Creating run"
call_json "POST" "/runs" "$(printf '{"config":{},"document_ids":["%s"]}' "${DOC_ID}")"
[[ "${RESPONSE_STATUS}" == "200" || "${RESPONSE_STATUS}" == "201" ]] || abort "Run creation failed (${RESPONSE_STATUS})"
RUN_ID="$(jq -r '.run_id' "${TMP_BODY}")"
[[ -n "${RUN_ID}" && "${RUN_ID}" != "null" ]] || abort "run_id missing"

QUESTION="Who are the stakeholders?"
ASK_BODY="$(printf '{"run_id":"%s","question":"%s","debug":true}' "${RUN_ID}" "${QUESTION}")"

echo "[ci-e2e] Asking question"
call_json "POST" "/chat/ask" "${ASK_BODY}"
[[ "${RESPONSE_STATUS}" == "200" || "${RESPONSE_STATUS}" == "201" ]] || abort "Ask failed (${RESPONSE_STATUS})"

CITATIONS_COUNT="$(jq '.citations | length' "${TMP_BODY}")"
[[ "${CITATIONS_COUNT}" -gt 0 ]] || abort "Expected citations"

TRGM_FLAG="$(jq -r '.debug_meta.trgm_available // empty' "${TMP_BODY}")"
if [[ "${TRGM_FLAG}" != "true" ]]; then
  if [[ "${TRGM_AVAILABLE_DB}" == "t" || "${TRGM_AVAILABLE_DB}" == "true" || "${TRGM_AVAILABLE_DB}" == "1" ]]; then
    echo "[ci-e2e] Warning: debug_meta.trgm_available missing; pg_trgm confirmed in DB"
  else
    abort "pg_trgm unavailable (debug_meta missing and DB check failed)"
  fi
fi

echo "[ci-e2e] E2E gate succeeded (doc_id=${DOC_ID} run_id=${RUN_ID})"
