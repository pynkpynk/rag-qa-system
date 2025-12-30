# Work Order Template

## Title
Freeze public API contracts and document response schemas

## Goal
What user-visible behavior or capability will be added/changed?

- Publish a stable public API contract that documents the main endpoints (health, documents, runs, chat/ask) including request/response examples and common error payloads.
- Attach FastAPI `response_model` declarations to those endpoints so generated OpenAPI + docs/api_contract.md stay aligned with runtime behavior.
- Add lightweight contract tests to ensure key endpoints return the documented status codes and required fields using the public schemas.

## Non-goals
What will NOT be changed in this work order?

- No behavioral changes to debug or internal endpoints (e.g., `/api/_debug/**`, `/api/_smoke/**`).
- No modifications to upload/ingestion pipelines beyond schema annotations.
- No new authentication mechanisms; existing dev/admin tokens continue to be used.

## Context
- Current behavior:
  - Public endpoints exist but lack a single contract doc and consistent `response_model` declarations.
  - Tests do not assert the current response shapes, so regressions can slip in unnoticed.
- Problem:
  - Without a documented contract, clients guess the schema and break when fields change.
  - Missing schemas hinder OpenAPI consumers and governance reviews.
- Why now:
  - We are approaching a release that requires a frozen contract for clients and compliance.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: No runtime changes besides schema validation; endpoints still respond as before.
- [ ] Edge cases covered: Errors (401/403/422/500) documented with example payloads.
- [ ] Tests added/updated: Contract tests cover success and at least one auth failure path.
- [ ] No unnecessary abstraction: Reuse existing serializers/mappers, do not add new layers.
- [ ] No duplicate utilities introduced: New schemas reuse existing DTOs where possible.
- [ ] Docs updated if public interfaces changed: `docs/api_contract.md` describes the endpoints and excludes debug routes.

## Constraints / Budgets
- Max modified files: 10
- Max new public APIs: 0 (schema classes only)
- Dependency additions: forbidden

## Design notes (contracts/interfaces)
- Inputs:
  - `GET /api/health`
  - `GET /api/docs/{id}`, `GET /api/docs`, `POST /api/docs/upload` (documented as list/detail/upload but no schema change)
  - `GET /api/runs`, `POST /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/attach_docs`, `DELETE /api/runs/{id}`
  - `POST /api/chat/ask`
- Outputs:
  - Health payload `{app, version, status, time_utc}`
  - Documents list/detail responses containing `document_id`, `status`, `owner_sub`, etc. (derive from existing serializer output)
  - Runs list/detail responses using existing `_serialize_*` helpers
  - Chat response `{answer, citations, run_id, request_id}` plus optional `retrieval_debug`, `debug_meta`
- Error cases:
  - 401/403/404 unified error payload via exception handler
  - 422 validation errors with `{error: {code: "VALIDATION_ERROR", message, details}}`
  - 500 internal error payload
- Authorization rules (if any): owner_sub-based access enforced via `ensure_run_access` and document owner checks. Auth notes must remind that cross-tenant access returns 404 when unauthorized.

## Implementation plan (5–10 bullets)
1) Add `docs/api_contract.md` describing the scoped endpoints, request/response examples, and error payloads while explicitly excluding debug routes.
2) Create new Pydantic response schemas (or reuse existing ones) and set `response_model` on health, document list/detail, document upload response, run endpoints, and `/api/chat/ask`.
3) Ensure schemas capture optional debug fields without altering runtime behavior (use `Field(default=None)` or `list[...] | None`).
4) Update docs router serializers if needed to conform to schemas without reprocessing data.
5) Implement `tests/test_api_contract.py` using FastAPI `TestClient` to hit each endpoint (with OPENAI_OFFLINE=1) and assert minimal keys + error cases.
6) Leverage guardrail patterns `python_fastapi/router_secured_example.py`, `python_fastapi/schemas.py`, and `python_fastapi/test_example.py` for structure and testing style references.
7) Run pytest locally to ensure the new contract tests and existing suites pass.

## Test plan
- Unit tests:
  - `tests/test_api_contract.py` covering health, docs (list/detail), runs (list/detail/create), and chat/ask success with offline stubs.
- Integration/smoke tests (if needed):
  - Existing backend smoke will implicitly cover schema wiring; no new integration tests required.
- Manual checks (optional):
  - Verify `/api/docs` and `/api/runs` still render in Swagger UI with the new response models.

## Security considerations
- New attack surface:
  - None; documenting endpoints only. Ensure tests do not leak tokens.
- Data handling:
  - Schemas must not expose sensitive identifiers (owner_sub) unless already in responses; follow current behavior.
- AuthN/AuthZ changes:
  - None. Tests should respect existing auth dependencies (dev principal) and include a 401 scenario for missing credentials.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared for review
