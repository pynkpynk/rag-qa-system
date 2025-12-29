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
fi

HOST="${DEV_SERVER_HOST:-127.0.0.1}"
PORT="${DEV_SERVER_PORT:-8000}"

wait_for_exit() {
    local pid="$1"
    for _ in {1..50}; do
        if ! ps -p "${pid}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    return 1
}

kill_pid_gracefully() {
    local pid="$1"
    if ! ps -p "${pid}" >/dev/null 2>&1; then
        return 0
    fi
    kill -TERM "${pid}" >/dev/null 2>&1 || true
    if wait_for_exit "${pid}"; then
        return 0
    fi
    kill -KILL "${pid}" >/dev/null 2>&1 || true
    wait_for_exit "${pid}" || true
}

stop_pid_file() {
    if [[ ! -f "${PID_FILE}" ]]; then
        return 1
    fi
    local pid
    pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -z "${pid}" ]]; then
        rm -f "${PID_FILE}"
        return 1
    fi
    echo "[dev_down] Stopping dev server (pid ${pid})..."
    kill_pid_gracefully "${pid}"
    rm -f "${PID_FILE}"
    return 0
}

stop_port_processes() {
    if ! command -v lsof >/dev/null 2>&1; then
        return
    fi
    local pids
    pids="$(lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2}' | sort -u)"
    if [[ -z "${pids}" ]]; then
        return
    fi
    for pid in ${pids}; do
        if ! ps -p "${pid}" >/dev/null 2>&1; then
            continue
        fi
        local cmd
        cmd="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
        if [[ -z "${cmd}" ]]; then
            continue
        fi
        if [[ "${cmd}" == *"uvicorn"* && "${cmd}" == *"app.main:app"* && "${cmd}" == *"--port ${PORT}"* ]]; then
            echo "[dev_down] Terminating lingering uvicorn process pid=${pid} (${cmd})"
            kill_pid_gracefully "${pid}"
        fi
    done
}

stop_pid_file || echo "[dev_down] No active pid file; checking port ${PORT}..."
stop_port_processes
echo "[dev_down] Done."
