#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="8000"
FRONTEND_PORT="5173"

cleanup() {
  echo ""
  echo "Stopping dev servers..."
  "${ROOT_DIR}/scripts/kill_port.sh" "${BACKEND_PORT}" || true
  "${ROOT_DIR}/scripts/kill_port.sh" "${FRONTEND_PORT}" || true
}

trap cleanup EXIT INT TERM

echo "Starting backend..."
("${ROOT_DIR}/scripts/dev_backend.sh") &
BACK_PID=$!

echo "Starting frontend..."
("${ROOT_DIR}/scripts/dev_frontend.sh") &
FRONT_PID=$!

echo ""
echo "Backend : http://127.0.0.1:${BACKEND_PORT}"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
echo ""
echo "Press Ctrl+C to stop."

wait -n "${BACK_PID}" "${FRONT_PID}"
