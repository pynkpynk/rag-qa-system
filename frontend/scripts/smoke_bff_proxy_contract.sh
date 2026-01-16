#!/usr/bin/env bash
set -euo pipefail

WEB_BASE=${WEB_BASE:-http://127.0.0.1:3000}
DEV_SUB=${DEV_SUB:-dev|user}
PDF_TMP=$(mktemp "${TMPDIR:-/tmp}/ragqa_smoke_pdf.XXXXXX.pdf")
TMP_FILES=()

cleanup() {
  rm -f "$PDF_TMP"
  for f in "${TMP_FILES[@]:-}"; do
    rm -f "$f"
  done
}
trap cleanup EXIT

log() {
  printf '[bff-smoke] %s\n' "$*" >&2
}

fail() {
  printf '[bff-smoke] ERROR: %s\n' "$*" >&2
  exit 1
}

python3 - <<'PY' >"$PDF_TMP"
import base64, sys
data = """JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgaHR0cDovL3d3dy5yZXBvcnRsYWIuY29tCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9UeXBlIC9Gb250Ci9TdWJ0eXBlIC9UeXBlMQovTmFtZSAvRjEKL0Jhc2VGb250IC9IZWx2ZXRpY2EKL0VuY29kaW5nIC9XaW5BbnNpRW5jb2RpbmcKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0xlbmd0aCAxMTAKPj4Kc3RyZWFtCkJUCi9GMSAxMiBUZgowIDAgVGQKKFJBRyBRQSBTeXN0ZW0gc21va2UgdGVzdCBQREYpIFRqCjAgLTE0IFRkCihUaGlzIFBERiBoYXMgZXh0cmFjdGFibGUgdGV4dC4pIFRqCkVUCmVuZHN0cmVhbQplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUGFyZW50IDYgMCBSCi9NZWRpYUJveCBbMCAwIDYxMiA3OTJdCi9Db250ZW50cyAzIDAgUgovUmVzb3VyY2VzIDw8Ci9Gb250IDw8Ci9GMSAyIDAgUgo+Pgo+Pgo+PgplbmRvYmoKNSAwIG9iago8PAovQ3JlYXRvciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gd3d3LnJlcG9ydGxhYi5jb20pCi9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gd3d3LnJlcG9ydGxhYi5jb20pCi9UaXRsZSAoKQovQXV0aG9yICgpCi9TdWJqZWN0ICgpCi9LZXl3b3JkcyAoKQovQ3JlYXRpb25EYXRlIChEOjIwMjYwMTE2MDAwMDAwKzAwJzAwJykKPj4KZW5kb2JqCjYgMCBvYmoKPDwKL1R5cGUgL1BhZ2VzCi9LaWRzIFs0IDAgUl0KL0NvdW50IDEKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDYgMCBSCj4+CmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYKMDAwMDAwMDA5OSAwMDAwMCBuCjAwMDAwMDAxNjAgMDAwMDAgbgowMDAwMDAwMzAyIDAwMDAwIG4KMDAwMDAwMDQ2NiAwMDAwMCBuCjAwMDAwMDA2ODIgMDAwMDAgbgowMDAwMDAwOTM0IDAwMDAwIG4KMDAwMDAwMTAyMyAwMDAwMCBuCnRyYWlsZXIKPDwKL1NpemUgOAovUm9vdCA3IDAgUgovSW5mbyA1IDAgUgo+PgpzdGFydHhyZWYKMTA4NwolJUVPRgo="""
sys.stdout.buffer.write(base64.b64decode(data))
PY

if ! head -c 4 "$PDF_TMP" | grep -q "%PDF"; then
  fail "Embedded PDF is corrupted or missing %PDF header"
fi

resp_status=""
resp_body=""

perform_request() {
  local method=$1
  local path=$2
  local header_mode=$3
  shift 3
  local body_file
  body_file=$(mktemp "${TMPDIR:-/tmp}/ragqa_smoke_body.XXXXXX")
  TMP_FILES+=("$body_file")
  local curl_cmd=(curl -sS -X "$method" -o "$body_file" -w '%{http_code}')
  if [[ "$header_mode" == "with-dev" ]]; then
    curl_cmd+=(-H "x-dev-sub: ${DEV_SUB}")
  fi
  curl_cmd+=("$@")
  curl_cmd+=("${WEB_BASE}${path}")
  resp_status=$("${curl_cmd[@]}")
  resp_body=$(cat "$body_file")
}

body_preview() {
  printf '%s' "$resp_body" | head -c 200
}

log "1) GET /api/docs with x-dev-sub"
perform_request GET "/api/docs" with-dev
if [[ "$resp_status" != "200" ]]; then
  fail "Expected 200, got $resp_status with body: $(body_preview)"
fi
printf '%s' "$resp_body" | python3 -c '
import json, sys
data = json.load(sys.stdin)
if not isinstance(data, list):
    raise SystemExit("docs payload is not a list")
for i, doc in enumerate(data):
    if not isinstance(doc, dict):
        raise SystemExit(f"docs[{i}] is not an object")
    for key in ("document_id", "filename", "status"):
        if key not in doc:
            raise SystemExit(f"docs[{i}] missing key {key!r}")
'

log "2) GET /api/docs without x-dev-sub should fail auth"
perform_request GET "/api/docs" without-dev
if [[ "$resp_status" != "401" ]]; then
  fail "Expected 401 without dev header, got $resp_status"
fi
if [[ "$resp_body" != *"NOT_AUTHENTICATED"* && "$resp_body" != *"Missing bearer token"* ]]; then
  fail "Expected NOT_AUTHENTICATED error, got: $(body_preview)"
fi

log "3) POST /api/docs/upload with extractable PDF"
perform_request POST "/api/docs/upload" with-dev -F "file=@${PDF_TMP};type=application/pdf;filename=smoke.pdf"
case "$resp_status" in
  200|201) ;;
  *) fail "Upload expected 200 or 201, got $resp_status with body: $(body_preview)" ;;
esac
if [[ "$resp_body" == *"PDF_PARSE_FAILED"* || "$resp_body" == *"No extractable content"* ]]; then
  fail "Upload failed parse check: $(body_preview)"
fi
doc_id=$(
  printf '%s' "$resp_body" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as exc:
    raise SystemExit(f"upload response not JSON: {exc}")
if isinstance(data, dict) and data.get("error"):
    raise SystemExit(f"upload returned error: {data['error']}")
doc_id = data.get("document_id") or data.get("document", {}).get("document_id")
if not doc_id:
    raise SystemExit("document_id missing from upload response")
print(doc_id, end="")
' || true
)
if [[ -z "$doc_id" ]]; then
  fail "Could not determine uploaded document_id"
fi
log "Upload returned document_id=$doc_id"

log "4) DELETE /api/docs/${doc_id} returns 204 with empty body"
perform_request DELETE "/api/docs/${doc_id}" with-dev
if [[ "$resp_status" != "204" ]]; then
  fail "Expected 204 delete status, got $resp_status with body: $(body_preview)"
fi
trimmed=$(printf '%s' "$resp_body" | tr -d $'\r\n\t ')
if [[ -n "$trimmed" ]]; then
  fail "204 response should be empty, got: $(body_preview)"
fi

log "Smoke checks passed against ${WEB_BASE}"
