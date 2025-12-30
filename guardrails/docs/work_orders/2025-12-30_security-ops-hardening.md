# Work Order Template

## Title
Security/Ops hardening v1

## Goal
Ensure the RAG QA backend enforces production-safe defaults: prod responses never expose debug data, uploads are validated (type/size/PDF sanity), secrets are not logged, and owner-based access controls continue to hold with regression tests.

## Non-goals
- No new product functionality or UX changes.
- No schema or database changes beyond safer validation.
- No frontend refactors beyond what existing tests already cover.

## Context
- Current behavior:
  - Debug metadata can still leak if prod flag mis-set.
  - Upload route does not enforce content-type/size/PDF header strictly.
  - Secret masking relies on convention; tests do not cover it.
  - Owner authorization lacks regression coverage for docs/runs endpoints.
- Problem:
  - Prod needs deterministic safety, especially around debug gating and uploads.
  - Missing contract tests could allow regressions.
- Why now:
  - Release readiness requires confidence that prod defaults are safe and tests catch regressions.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: prod env ignores debug flags and hides debug endpoints.
- [ ] Edge cases covered: upload rejects wrong type/oversize/invalid PDFs; owner access enforced for docs/runs.
- [ ] Tests added/updated: cover prod debug gating, upload validation, owner auth, log masking sanity.
- [ ] No unnecessary abstraction: reuse existing helpers/dependencies.
- [ ] No duplicate utilities introduced: leverage current settings/logging helpers.
- [ ] Docs updated if public interfaces changed: update ops/security notes if behavior changes.

## Constraints / Budgets
- Max modified files: 10
- Max new public APIs: 0 (reuse existing schemas/helpers)
- Dependency additions: forbidden

## Design notes (contracts/interfaces)
- Inputs: HTTP requests to /api/chat/ask (debug flag), /api/docs/upload, owner-targeted routes.
- Outputs: JSON error payloads per existing contract; no debug data in prod responses.
- Error cases: 413/415/422 for uploads; 401/404 for unauth/unauthorized; prod debug requests silently ignored.
- Authorization rules: owner_sub must match authenticated principal for docs/runs actions.

## Implementation plan (5–10 bullets)
1) Add helper to detect prod env in chat route and guard debug_meta/retrieval_debug + debug-only routes.
2) Expand docs upload handler to enforce content-type, file size (settings.max_upload_bytes), and PDF header checks.
3) Ensure logging mask filter is exercised; add unit test verifying Authorization token is redacted.
4) Review doc/run queries to confirm owner_sub filtering; adjust if necessary.
5) Add pytest coverage: prod debug gating, upload validation (type/size/header), owner access negative cases, log masking.
6) Run full pytest suite (OPENAI_OFFLINE=1) to confirm stability.

## Test plan
- Unit tests: logging redaction filter, prod debug suppression logic, upload validator helper.
- Integration tests: FastAPI TestClient scenarios for chat debug in prod, uploads (type/size/invalid PDF), owner auth across docs/runs endpoints.
- Manual checks (optional): n/a for this work order.

## Security considerations
- New attack surface: none (tightening existing behavior).
- Data handling: ensure uploads stored only after validation; debug payload suppressed in prod.
- AuthN/AuthZ changes: enforce owner_sub filtering with regression tests.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared for review
