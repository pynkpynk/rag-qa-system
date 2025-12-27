#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env.local"
PID_FILE="${BACKEND_DIR}/.devserver.pid"
PORT="${DEV_SERVER_PORT:-8000}"
HOST="${DEV_SERVER_HOST:-127.0.0.1}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[dev_up] ${ENV_FILE} not found. Copy backend/.env.example to .env.local and populate it." >&2
    exit 1
fi

if [[ -f "${PID_FILE}" ]]; then
    if pid=$(cat "${PID_FILE}" 2>/dev/null) && ps -p "${pid}" >/dev/null 2>&1; then
        echo "[dev_up] Dev server already running (pid ${pid}). Run backend/scripts/dev_down.sh first." >&2
        exit 1
    else
        rm -f "${PID_FILE}"
    fi
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if [[ -z "${PYTHON_BIN}" ]]; then
    echo "[dev_up] Could not find python interpreter." >&2
    exit 1
fi

REQUIRED_VARS=("ADMIN_SUBS" "AUTH0_DOMAIN" "AUTH0_AUDIENCE")
for key in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!key:-}" ]]; then
        echo "[dev_up] Required env ${key} is missing. Update ${ENV_FILE}." >&2
        exit 1
    fi
done

if [[ -n "${ADMIN_TOKEN:-}" ]]; then
    ADMIN_DEBUG_TOKEN_SHA256_LIST="$("${PYTHON_BIN}" - <<'PY'
import hashlib, os
token = os.environ.get("ADMIN_TOKEN", "")
print(hashlib.sha256(token.encode("utf-8")).hexdigest())
PY
)"
    export ADMIN_DEBUG_TOKEN_SHA256_LIST
fi

export ENABLE_RETRIEVAL_DEBUG="${ENABLE_RETRIEVAL_DEBUG:-1}"
export ENABLE_HYBRID="${ENABLE_HYBRID:-1}"
export ENABLE_TRGM="${ENABLE_TRGM:-1}"
export TRGM_K="${TRGM_K:-30}"
export RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH="${RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH:-0}"

cd "${BACKEND_DIR}"
echo "[dev_up] Starting uvicorn on ${HOST}:${PORT} via ${PYTHON_BIN} (reload enabled)"

cleanup() {
    rm -f "${PID_FILE}"
}
trap cleanup EXIT INT TERM

"${PYTHON_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload &
UVICORN_PID=$!
echo "${UVICORN_PID}" > "${PID_FILE}"
wait "${UVICORN_PID}"
