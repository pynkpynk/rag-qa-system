#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-}"
if [[ -z "${PORT}" ]]; then
  echo "Usage: ./scripts/kill_port.sh <port>"
  exit 1
fi

PIDS=$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN || true)
if [[ -z "${PIDS}" ]]; then
  echo "No process is listening on port ${PORT}"
  exit 0
fi

echo "Killing PID(s) on port ${PORT}: ${PIDS}"
kill ${PIDS} || true
