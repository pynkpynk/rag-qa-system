#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env.local"
PID_FILE="${BACKEND_DIR}/.devserver.pid"
LOG_FILE="${BACKEND_DIR}/.devserver.log"
DOTENV_HELPER="${SCRIPT_DIR}/_dotenv.sh"

if [[ -f "${DOTENV_HELPER}" ]]; then
    # shellcheck disable=SC1090
    source "${DOTENV_HELPER}"
fi

if [[ -f "${ENV_FILE}" ]]; then
    dotenv_load_preserve_existing "${ENV_FILE}"
fi

# ---- Required env for Settings (smoke defaults) ----
# NOTE:
# - Put this AFTER dotenv load, otherwise ".env.local" cannot override these values
# - Only apply in CI/smoke contexts so local dev isn't accidentally forced to dummy values

IS_CI=0
if [[ "${GITHUB_ACTIONS:-}" == "true" || "${CI:-}" == "true" || "${RAGQA_SMOKE:-0}" == "1" ]]; then
    IS_CI=1
fi

export CORS_ORIGIN="${CORS_ORIGIN:-http://localhost:5173,http://127.0.0.1:5173}"
if [[ "${IS_CI}" == "1" ]]; then
    export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-smoke-ci-dummy}"
    export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:////tmp/ragqa_smoke.db}"
fi

HOST="${DEV_SERVER_HOST:-127.0.0.1}"
PORT="${DEV_SERVER_PORT:-8000}"

if [[ -f "${PID_FILE}" ]]; then
    if pid=$(cat "${PID_FILE}" 2>/dev/null) && ps -p "${pid}" >/dev/null 2>&1; then
        echo "[dev_up] Dev server already running (pid ${pid}). Run backend/scripts/dev_down.sh first." >&2
        exit 1
    fi
    rm -f "${PID_FILE}"
fi

CHOSEN_PY="${PYTHON_BIN:-}"
if [[ -n "${CHOSEN_PY}" && ! -x "${CHOSEN_PY}" ]]; then
    echo "[dev_up] PYTHON_BIN is set but not executable: ${CHOSEN_PY}" >&2
    exit 1
fi
if [[ -z "${CHOSEN_PY}" ]]; then
    if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
        CHOSEN_PY="${REPO_ROOT}/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        CHOSEN_PY="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        CHOSEN_PY="$(command -v python)"
    else
        echo "[dev_up] Could not find python interpreter." >&2
        exit 1
    fi
fi
PYTHON_BIN="${CHOSEN_PY}"
echo "[dev_up] Using python: ${PYTHON_BIN} ($("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'))"

if ! "${PYTHON_BIN}" - <<'PY'
import importlib
for mod in ("jose", "fastapi"):
    importlib.import_module(mod)
PY
then
    cat >&2 <<'EOF'
[dev_up] Python environment missing required packages (e.g., jose, fastapi).
[dev_up] Activate the repo venv (.venv) and run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
EOF
    exit 1
fi

# -------------------------------
# Env validation (mode-aware)
# -------------------------------
AUTH_MODE_EFFECTIVE="${AUTH_MODE:-auth0}"
AUTH_MODE_LOWER="$(printf '%s' "${AUTH_MODE_EFFECTIVE}" | tr '[:upper:]' '[:lower:]')"

if [[ "${AUTH_MODE_LOWER}" != "dev" && "${AUTH_MODE_LOWER}" != "demo" ]]; then
    # Auth0 mode requires these to be present (CI doesn't have .env.local)
    REQUIRED_VARS=("AUTH0_DOMAIN" "AUTH0_AUDIENCE" "AUTH0_ISSUER")
    for key in "${REQUIRED_VARS[@]}"; do
        if [[ -z "${!key:-}" ]]; then
            echo "[dev_up] Required env ${key} is missing. Check ${ENV_FILE}." >&2
            exit 1
        fi
    done
fi

# ADMIN_SUBS is optional, but show a hint if empty (especially useful in CI)
if [[ -z "${ADMIN_SUBS:-}" ]]; then
    echo "[dev_up] Note: ADMIN_SUBS is empty. Admin debug features may be unavailable." >&2
fi

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
export ADMIN_DEBUG_STRATEGY="${ADMIN_DEBUG_STRATEGY:-firstk}"

cd "${BACKEND_DIR}"
RELOAD_FLAG="enabled"
if [[ "${DEV_RELOAD:-1}" == "0" ]]; then
    RELOAD_FLAG="disabled"
fi

echo "[dev_up] Starting uvicorn on ${HOST}:${PORT} via ${PYTHON_BIN} (reload ${RELOAD_FLAG})"
echo "[dev_up] Flags: AUTH_MODE=${AUTH_MODE_EFFECTIVE} ADMIN_DEBUG_STRATEGY=${ADMIN_DEBUG_STRATEGY} ENABLE_RETRIEVAL_DEBUG=${ENABLE_RETRIEVAL_DEBUG} RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH=${RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH} MAX_REQUEST_BYTES=${MAX_REQUEST_BYTES:-unset} RATE_LIMIT_ENABLED=${RATE_LIMIT_ENABLED:-0}"
echo "[dev_up] Logs: ${LOG_FILE}"

touch "${LOG_FILE}"
: > "${LOG_FILE}"

UVICORN_CMD=("${PYTHON_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}")
if [[ "${DEV_RELOAD:-1}" != "0" ]]; then
    UVICORN_CMD+=(--reload)
fi

SETSID_BIN="$(command -v setsid || true)"
if [[ -n "${SETSID_BIN}" ]]; then
    "${SETSID_BIN}" "${UVICORN_CMD[@]}" >> "${LOG_FILE}" 2>&1 &
else
    nohup "${UVICORN_CMD[@]}" >> "${LOG_FILE}" 2>&1 &
fi
UVICORN_PID=$!
echo "${UVICORN_PID}" > "${PID_FILE}"

HEALTH_URL="http://${HOST}:${PORT}/api/health"
for attempt in {1..10}; do
    if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
        echo "[dev_up] Dev server is healthy at ${HEALTH_URL}"
        exit 0
    fi
    sleep 0.5
done

echo "[dev_up] Server failed to start. Showing last 200 log lines:"
tail -n 200 "${LOG_FILE}" || true
if ps -p "${UVICORN_PID}" >/dev/null 2>&1; then
    kill -TERM "${UVICORN_PID}" >/dev/null 2>&1 || true
fi
rm -f "${PID_FILE}"
exit 1
