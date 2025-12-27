#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${BACKEND_DIR}/.devserver.pid"

if [[ ! -f "${PID_FILE}" ]]; then
    echo "[dev_down] No dev server pid file found."
    exit 0
fi

pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
if [[ -z "${pid}" ]]; then
    rm -f "${PID_FILE}"
    echo "[dev_down] Stale pid file removed."
    exit 0
fi

if ! ps -p "${pid}" >/dev/null 2>&1; then
    rm -f "${PID_FILE}"
    echo "[dev_down] Process ${pid} not running. Cleaned up pid file."
    exit 0
fi

echo "[dev_down] Stopping dev server (pid ${pid})..."
kill "${pid}" >/dev/null 2>&1 || true

for _ in {1..20}; do
    if ! ps -p "${pid}" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

rm -f "${PID_FILE}"
echo "[dev_down] Dev server stopped."
