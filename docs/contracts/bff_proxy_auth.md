# BFF Proxy Auth Contract

This document captures the invariants the Next.js App Router proxy must honor to keep local development, demo flows, and production deployments aligned. Any change to the proxy or preview/upload/delete flows must update this contract and the smoke test.

## Authorization forwarding
- If the caller supplies an `Authorization` header, forward it verbatim. Never override or append tokens.
- If `Authorization` is absent **and** the request includes `x-dev-sub`, and the proxy targets a local backend (base URL contains `localhost` or `127.0.0.1`) while `NODE_ENV !== "production"`, inject `Authorization: Bearer ${RAGQA_DEV_TOKEN || "dev-token"}`.
- Otherwise, inject the demo token **only** when `RAGQA_INJECT_DEMO_TOKEN=1` *and* `RAGQA_DEMO_TOKEN` is set. If not enabled, leave `Authorization` empty so the backend returns `NOT_AUTHENTICATED`.

Example:
```
# For local dev with x-dev-sub
curl -H "x-dev-sub: dev|user" http://localhost:3000/api/docs
# Proxy injects Authorization: Bearer dev-token (or RAGQA_DEV_TOKEN value)
```

## `x-dev-sub` propagation
- UI flows (home screen, preview modal, uploads, deletes) must set `x-dev-sub` in local `AUTH_MODE=dev` scenarios using the `ragqa.ui.devSub` localStorage key (default `dev|user`). This allows the proxy to safely inject the dev token.

## `/api/docs` payload shape
- The `GET /api/docs` endpoint returns a JSON array of document objects. Each object includes `document_id`, `filename`, and `status` fields (plus any additional metadata). Downstream tooling (including the smoke script) relies on this array shape; do not wrap the list in another object without updating clients/tests.

## 204/205 upstream handling
- When the backend returns HTTP 204 or 205, the proxy must relay the status and filtered headers without buffering/parsing the body or inventing JSON/content-type values. These responses should never be wrapped in `UPSTREAM_INVALID_JSON`.

## Encoding / decoding
- The proxy forces `Accept-Encoding: identity` on upstream fetches to avoid compressed payloads the proxy would need to re-decode.
- Whenever the proxy buffers or re-serializes a body (JSON, text, binary), it must remove `content-encoding`, `content-length`, and `transfer-encoding` headers before responding so browsers do not attempt double-decoding (e.g., `ERR_CONTENT_DECODING_FAILED`).

## Size limits / 413 propagation
- The proxy must pass through backend size guards: requests exceeding `MAX_REQUEST_BYTES` must surface as HTTP 413 `Request body too large`, preserving the backend error payload so callers know the request needs trimming.

Refer to `frontend/scripts/smoke_bff_proxy_contract.sh` for runnable checks that exercise these guarantees end-to-end.
