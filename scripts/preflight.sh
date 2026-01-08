#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PY_BIN="./.venv/bin/python"
if [[ ! -x "$PY_BIN" ]]; then
  PY_BIN="python"
fi

export APP_ENV="dev"
export AUTH_MODE="dev"
export DEV_SUB="test-user"
export CORS_ORIGIN="http://localhost:5173"
if [[ -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ragqa_test"
else
  export DATABASE_URL
fi
echo "[preflight] DATABASE_URL=${DATABASE_URL}"

compile_targets=()
for target in "backend/app" "backend/tests"; do
  if [[ -d "$target" ]]; then
    compile_targets+=("$target")
  fi
done

if [[ ${#compile_targets[@]} -gt 0 ]]; then
  "$PY_BIN" -m compileall "${compile_targets[@]}"
fi

if [[ -d "backend/tests" ]]; then
  "$PY_BIN" -m pytest -q backend/tests
fi
