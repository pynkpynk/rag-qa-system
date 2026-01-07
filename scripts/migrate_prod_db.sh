#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PSQL_URL:-}" ]]; then
  echo "PSQL_URL env var is required" >&2
  exit 1
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${repo_root}/backend/.venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then
  python_bin="python"
fi

proto="${PSQL_URL%%://*}"
if [[ "${proto}" == "${PSQL_URL}" ]]; then
  proto="unknown"
fi
echo "[migrate] target database protocol=${proto}"

run_alembic() {
  env DATABASE_URL="${PSQL_URL}" PYTHONPATH=backend \
    "${python_bin}" -m alembic -c backend/alembic.ini "$@"
}

echo "[migrate] Current revision:"
run_alembic current

echo "[migrate] Upgrading to head..."
run_alembic upgrade head

echo "[migrate] Revision after upgrade:"
run_alembic current

echo "[migrate] Done."
