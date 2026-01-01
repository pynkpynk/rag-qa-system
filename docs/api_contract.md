# Public API Contract

This document describes the JSON contract for the RAG QA backend (`/api/**`). Internal diagnostics (`/api/_debug/**`, `/api/_smoke/**`) may change without notice unless explicitly documented below. File/streaming responses (e.g., PDF downloads) are called out separately.

## Common Error Shape
All structured errors reuse the payload emitted by `app.main._error_payload`.

```json
{
  "error": {
    "code": "RUN_FORBIDDEN",
    "message": "run is active (status=processing); refuse to delete"
  }
}
```

Typical codes:

| Status | Code               | Notes                                      |
|-------:|--------------------|--------------------------------------------|
| 401    | `NOT_AUTHENTICATED`| Missing/invalid bearer token in Auth0 mode |
| 403    | `RUN_FORBIDDEN`    | Caller authenticated but not allowed       |
| 404    | `NOT_FOUND`        | Resource hidden when owner_sub mismatch    |
| 409    | `HTTP_ERROR`       | Conflicts such as deleting busy runs       |
| 422    | `VALIDATION_ERROR` | Request validation failure                 |
| 429    | `HTTP_ERROR`       | Rate limiting                              |
| 500    | `INTERNAL_ERROR`   | Unhandled server error                     |

## Endpoint Summary

| Method | Path                                   | Response schema                                 |
|--------|----------------------------------------|-------------------------------------------------|
| GET    | `/api/health`                          | `HealthResponse`                                |
| POST   | `/api/docs/upload`                     | `DocumentUploadResponse`                        |
| GET    | `/api/docs`                            | `list[DocumentListItem]`                        |
| GET    | `/api/docs/{document_id}`              | `DocumentDetailResponse`                        |
| GET    | `/api/docs/{document_id}/pages/{page}` | `list[DocumentPageChunkItem]`                   |
| POST   | `/api/docs/{document_id}/reindex`      | `DocumentReindexResponse`                       |
| DELETE | `/api/docs/{document_id}`              | `204 No Content`                                |
| GET    | `/api/docs/{document_id}/download`     | File/redirect (PDF)                             |
| GET    | `/api/docs/{document_id}/view`         | File/inline PDF                                 |
| GET    | `/api/runs`                            | `list[RunListItem]`                             |
| POST   | `/api/runs`                            | `RunDetailResponse`                             |
| GET    | `/api/runs/{run_id}`                   | `RunDetailResponse`                             |
| POST   | `/api/runs/{run_id}/attach_docs`       | `RunDetailResponse`                             |
| DELETE | `/api/runs/{run_id}`                   | `RunDeleteResponse`                             |
| DELETE | `/api/runs`                            | `RunCleanupResponse`                            |
| GET    | `/api/chunks/{chunk_id}`               | `ChunkResponse`                                 |
| GET    | `/api/chunks/health`                   | `ChunkHealthResponse`                           |
| POST   | `/api/search`                          | `SearchResponse`                                |
| POST   | `/api/chat/ask`                        | `ChatResponse`                                  |
| GET    | `/api/_debug/aws-whoami`               | `DebugAwsWhoAmIResponse` (requires DEBUG token) |
| GET    | `/api/_debug/s3-head`                  | `DebugS3HeadResponse` (requires DEBUG token)    |

## Health
`GET /api/health`

```json
{
  "app": "RAG QA System",
  "version": "0.1.0",
  "status": "ok",
  "time_utc": "2025-12-30T10:00:00+00:00",
  "app_env": "prod",
  "auth_mode": "demo",
  "git_sha": "abc1234",
  "llm_enabled": true,
  "openai_offline": false,
  "openai_key_present": true
}
```

## Documents
Authentication: bearer token required. In multi-tenant mode a document is only visible to its `owner_sub`. Non-owners receive `404 NOT_FOUND` to hide existence. Missing/invalid tokens return `401 NOT_AUTHENTICATED`.

### Upload (multipart)
`POST /api/docs/upload`

Fields: `file` (PDF). Response:
```json
{
  "document_id": "doc_456",
  "filename": "design.pdf",
  "status": "indexed",
  "dedup": false
}
```

### List
`GET /api/docs`
```json
[
  {
    "document_id": "doc_123",
    "filename": "report.pdf",
    "status": "indexed",
    "error": null
  }
]
```

### Detail
`GET /api/docs/{document_id}`
```json
{
  "document_id": "doc_123",
  "filename": "report.pdf",
  "status": "indexed",
  "error": null,
  "content_hash": "abc123",
  "storage_key": "uploads/doc_123/file.pdf",
  "meta": {"pages": 12},
  "created_at": "2025-12-25T09:30:00+00:00"
}
```

### Page chunks
`GET /api/docs/{document_id}/pages/{page}`
```json
[
  {"chunk_id": "chunk_1", "chunk_index": 0, "text": "..."}
]
```

### Reindex
`POST /api/docs/{document_id}/reindex`
```json
{"document_id": "doc_123", "queued": true}
```
If indexing is disabled the response becomes:
```json
{"document_id": "doc_123", "queued": false, "reason": "OPENAI_API_KEY not configured"}
```

### Download / View
`GET /api/docs/{document_id}/download` and `/view` stream PDFs (either via `FileResponse` or S3 redirect). They do not return JSON.

### Delete
`DELETE /api/docs/{document_id}` ⇒ `204 No Content` with owner-sub enforcement.

## Runs
Runs are owned by `owner_sub`. Admins may pass `?all=true` to list all runs; non-admins see their own.

### List
`GET /api/runs`
```json
[
  {
    "run_id": "run_123",
    "created_at": "2025-12-25T09:30:00+00:00",
    "status": "created",
    "document_ids": ["doc_123"]
  }
]
```

### Create
`POST /api/runs`
```json
{
  "config": {"mode": "library"},
  "document_ids": ["doc_123"]
}
```
Response is `RunDetailResponse` containing config, status, error, and attached document_ids.

### Detail / Attach / Delete
- `GET /api/runs/{run_id}` → `RunDetailResponse`
- `POST /api/runs/{run_id}/attach_docs` → `RunDetailResponse`
- `DELETE /api/runs/{run_id}` → `RunDeleteResponse` (and 409 when status protected)

### Cleanup
`DELETE /api/runs?older_than_days=7&dry_run=true`
```json
{
  "dry_run": true,
  "older_than_days": 7,
  "cutoff_utc": "2025-12-01T00:00:00+00:00",
  "limit": 50,
  "candidates": [ {"run_id": "run_1", "created_at": "...", "status": "created", "document_ids": []} ],
  "skipped": [],
  "count": 1
}
```
When `dry_run=false` the payload switches to `deleted_count`, `deleted_run_ids`, and `skipped`.

## Chunks & Search
- `GET /api/chunks/health` → `ChunkHealthResponse {"ok": true, "principal_sub": "auth0|abc"}`
- `GET /api/chunks/{chunk_id}` → `ChunkResponse` (requires document ownership run guard)
- `POST /api/search` → `SearchResponse` (hybrid hits + optional debug)

## Chat / Ask
`POST /api/chat/ask`

Request example:
```json
{ "question": "Summarize project risks", "document_ids": ["doc_456"] }
```
Either `run_id` or `document_ids` may be provided to scope retrieval (not both). When neither is set, the
query falls back to the caller’s entire library/run context.
Response:
```json
{
  "answer": "- [S1] ...",
  "citations": [{"source_id": "S1", "page": 2, "filename": "report.pdf"}],
  "run_id": "run_123",
  "request_id": "req-123",
  "retrieval_debug": {"strategy": "hybrid_rrf_by_run", "count": 3},
  "debug_meta": {"feature_flag_enabled": true, "payload_debug": true, "is_admin": false, "include_debug": false, "auth_mode_dev": true, "used_trgm": false, "used_fts": true, "fts_skipped": false}
}
```
`retrieval_debug` only appears when admin debug gating allows it. `debug_meta` is boolean-only and only returned when `payload.debug=true` and the global flag is enabled.

## Debug (non-public)
The following routes require `DEBUG_TOKEN` and are excluded from public SLAs, but still declare Pydantic schemas:
- `/api/_debug/aws-whoami` → AWS identity metadata (no secrets)
- `/api/_debug/s3-head?key=...` → S3 object metadata summary
