#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env.local"
PID_FILE="${BACKEND_DIR}/.devserver.pid"
DOTENV_HELPER="${SCRIPT_DIR}/_dotenv.sh"

if [[ -f "${DOTENV_HELPER}" ]]; then
    # shellcheck disable=SC1090
    source "${DOTENV_HELPER}"
fi

if [[ -f "${ENV_FILE}" ]]; then
    dotenv_load_preserve_existing "${ENV_FILE}"
    echo "backend/.env.local: FOUND"
else
    echo "backend/.env.local: MISSING"
fi

HOST="${DEV_SERVER_HOST:-127.0.0.1}"
PORT="${DEV_SERVER_PORT:-8000}"

echo "Configured host: ${HOST}"
echo "Configured port: ${PORT}"
echo "AUTH_MODE=${AUTH_MODE:-auth0}"
echo "ADMIN_DEBUG_STRATEGY=${ADMIN_DEBUG_STRATEGY:-firstk}"
echo "ENABLE_RETRIEVAL_DEBUG=${ENABLE_RETRIEVAL_DEBUG:-1}"
echo "RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH=${RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH:-0}"

if [[ -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    echo "PID file: ${PID_FILE} -> ${pid}"
else
    echo "PID file: not found"
fi

if command -v lsof >/dev/null 2>&1; then
    echo
    echo "Processes listening on port ${PORT}:"
    lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || echo "  (none)"
else
    echo "lsof not available; skipping port scan."
fi
