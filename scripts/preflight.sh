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
