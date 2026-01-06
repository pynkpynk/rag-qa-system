#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE:-}" ]]; then
  echo "API_BASE env var is required" >&2
  exit 1
fi
if [[ -z "${TOKEN:-}" ]]; then
  echo "TOKEN env var is required" >&2
  exit 1
fi

token_prefix="${TOKEN:0:8}"
echo "[smoke] API_BASE=${API_BASE} token_prefix=${token_prefix}"

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

run_request() {
  local method="$1"
  local url="$2"
  shift 2
  local body_file
  body_file="$(mktemp "${tmpdir}/body.XXXXXX")"
  local status
  set +e
  status=$(
    curl -sS -o "${body_file}" -w "%{http_code}" \
      "$@" \
      -X "${method}" \
      "${url}"
  )
  local curl_rc=$?
  set -e
  if [[ ${curl_rc} -ne 0 ]]; then
    echo "[smoke] curl error rc=${curl_rc} (${method} ${url})" >&2
    if [[ -s "${body_file}" ]]; then
      cat "${body_file}" >&2
    else
      echo "(no body captured)" >&2
    fi
    exit 1
  fi
  if [[ ${status} =~ ^2 ]]; then
    if command -v jq >/dev/null 2>&1; then
      jq . "${body_file}" || cat "${body_file}"
    else
      cat "${body_file}"
    fi
    return 0
  fi
  echo "[smoke] ${method} ${url} failed (status ${status})" >&2
  if [[ -s "${body_file}" ]]; then
    cat "${body_file}" >&2
  else
    echo "(no body captured)" >&2
  fi
  exit 1
}

echo "[smoke] 1/3 GET /api/health"
run_request GET "${API_BASE%/}/api/health"

echo "[smoke] 2/3 GET /api/chunks/health"
run_request GET "${API_BASE%/}/api/chunks/health" \
  -H "Authorization: Bearer ${TOKEN}"

echo "[smoke] 3/3 POST /api/search"
run_request POST "${API_BASE%/}/api/search" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"q":"example","mode":"library","limit":5,"debug":true}'

echo "[smoke] OK"
