#!/usr/bin/env bash
set -euo pipefail

WEB_BASE=${WEB_BASE:-http://127.0.0.1:3000}
DEV_SUB=${DEV_SUB:-dev|user}
TMP_FILES=()
PDF_TMP=$(mktemp "${TMPDIR:-/tmp}/ragqa_smoke_pdf.XXXXXX.pdf")
TMP_FILES+=("$PDF_TMP")

cleanup() {
  for file in "${TMP_FILES[@]}"; do
    [[ -f "$file" ]] && rm -f "$file"
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
  fail "Embedded PDF missing %PDF header"
fi

resp_status=""
resp_body=""
resp_body_file=""
resp_header_file=""

make_tmp() {
  local file
  file=$(mktemp "${TMPDIR:-/tmp}/ragqa_smoke_tmp.XXXXXX")
  TMP_FILES+=("$file")
  printf '%s' "$file"
}

perform_request() {
  local method=$1
  local path=$2
  local header_mode=$3
  shift 3
  local body_file header_file
  body_file=$(make_tmp)
  header_file=$(make_tmp)
  local curl_cmd=(curl -sS -X "$method" -D "$header_file" -o "$body_file" -w '%{http_code}')
  if [[ "$header_mode" == "with-dev" ]]; then
    curl_cmd+=(-H "x-dev-sub: ${DEV_SUB}")
  fi
  curl_cmd+=("$@")
  curl_cmd+=("${WEB_BASE}${path}")
  resp_status=$("${curl_cmd[@]}")
  resp_body=$(cat "$body_file")
  resp_body_file="$body_file"
  resp_header_file="$header_file"
}

body_preview() {
  printf '%s' "$resp_body" | head -c 200
}

get_header_value() {
  local key
  key=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  [[ -n "$resp_header_file" ]] || return
  awk -v target="$key" '
    BEGIN { IGNORECASE = 1 }
    /^$/ { next }
    /^HTTP\// { next }
    {
      split($0, parts, ":")
      name = tolower(parts[1])
      if (name == target) {
        sub(/^[^:]+:\s*/, "", $0)
        print $0
        exit
      }
    }
  ' "$resp_header_file" | tr -d $'\r'
}

ensure_json_array() {
  python3 - "$resp_body_file" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    data = json.load(handle)
if not isinstance(data, list):
    raise SystemExit("docs payload is not a list")
for i, doc in enumerate(data):
    if not isinstance(doc, dict):
        raise SystemExit(f"docs[{i}] is not an object")
    for key in ("document_id", "filename", "status"):
        if key not in doc:
            raise SystemExit(f"docs[{i}] missing key {key!r}")
PY
}

log "1) GET /api/docs with x-dev-sub"
perform_request GET "/api/docs" with-dev
if [[ "$resp_status" != "200" ]]; then
  fail "Expected 200, got $resp_status with body: $(body_preview)"
fi
ensure_json_array || fail "Docs response is not valid JSON array"

log "1b) Encoding correctness with Accept-Encoding: br"
perform_request GET "/api/docs" with-dev -H "Accept-Encoding: br"
encoding=$(get_header_value "content-encoding")
if [[ -n "$encoding" ]]; then
  lower=${encoding,,}
  if [[ "$lower" == "br" ]]; then
    node - "$resp_body_file" <<'NODE' || fail "Brotli decoding failed"
const fs = require("fs");
const { brotliDecompressSync } = require("zlib");
const path = process.argv[1];
const raw = fs.readFileSync(path);
const decoded = brotliDecompressSync(raw).toString("utf8");
JSON.parse(decoded);
NODE
  else
    fail "Unexpected content-encoding '${encoding}'"
  fi
else
  python3 - "$resp_body_file" <<'PY' || fail "Encoding-free response is not JSON"
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    json.load(handle)
PY
fi

log "2) GET /api/docs with invalid Authorization should fail auth"
perform_request GET "/api/docs" without-dev -H "Authorization: Bearer invalid-token"
if [[ "$resp_status" != "401" ]]; then
  fail "Expected 401 for invalid token, got $resp_status"
fi
if [[ "$resp_body" != *"NOT_AUTHENTICATED"* && "$resp_body" != *"Missing bearer token"* ]]; then
  fail "Expected NOT_AUTHENTICATED error, got: $(body_preview)"
fi

log "3) POST /api/docs/upload with extractable PDF"
perform_request POST "/api/docs/upload" with-dev -F "file=@${PDF_TMP};type=application/pdf;filename=smoke.pdf"
case "$resp_status" in
  200|201) ;;
  *) fail "Upload expected 200/201, got $resp_status with body: $(body_preview)" ;;
esac
if [[ "$resp_body" == *"PDF_PARSE_FAILED"* || "$resp_body" == *"No extractable content"* ]]; then
  fail "Upload failed parse check: $(body_preview)"
fi
doc_id=$(
  python3 - "$resp_body_file" <<'PY' || true
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
if isinstance(data, dict) and data.get("error"):
    raise SystemExit(f"upload returned error: {data['error']}")
doc_id = data.get("document_id") or data.get("document", {}).get("document_id")
if not doc_id:
    raise SystemExit("document_id missing from upload response")
print(doc_id, end="")
PY
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
