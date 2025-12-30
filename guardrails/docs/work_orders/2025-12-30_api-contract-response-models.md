# Work Order Template

## Title
API contract + response models hardening

## Goal
Document the public REST contract, align FastAPI response models with the documented schemas, and add guard tests to prevent regressions.

## Non-goals
- No business logic or authorization changes beyond schema alignment.
- No new endpoints or feature work beyond documenting the existing ones.

## Context
- Current behavior: Many routers return dictionaries without declaring `response_model`. The API contract doc only partially covers endpoints.
- Problem: Without schemas/docs parity, generated OpenAPI + clients diverge and regressions slip in.
- Why now: The contract needs to be frozen before shipping GA and CI should enforce schema coverage.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: All JSON routes declare accurate `response_model` values.
- [ ] Edge cases covered: File/download routes are explicitly allowlisted so coverage tests skip them.
- [ ] Tests added/updated: Response-model coverage + contract smoke tests run in CI.
- [ ] No unnecessary abstraction: Schemas live under `app/schemas/**` and are reused.
- [ ] No duplicate utilities introduced: Tests reuse FastAPI TestClient fixtures.
- [ ] Docs updated if public interfaces changed: `docs/api_contract.md` lists endpoints + inputs/outputs.

## Constraints / Budgets
- Max modified files: 12
- Max new public APIs: 0 (schemas may be added but no runtime endpoints)
- Dependency additions: forbidden

## Design notes (contracts/interfaces)
- Inputs: HTTP requests hitting `/api/health`, `/api/docs/**`, `/api/runs/**`, `/api/chat/ask`, etc.
- Outputs: JSON payloads matching new Pydantic models; file/stream endpoints remain raw.
- Error cases: Continue using `{"error": {"code": str, "message": str}}` envelope.
- Authorization rules (if any): unchanged; tests rely on dev auth defaults.

## Implementation plan (5–10 bullets)
1) Expand `app/schemas/api_contract.py` to host document, run, chunk, and debug response models.
2) Update routers (health/docs/runs/chunks/debug/search/chat) to import and declare the schemas for JSON endpoints.
3) Maintain a central allowlist (file/stream endpoints) so coverage tests skip them.
4) Update `docs/api_contract.md` with the enumerated endpoints, request/response examples, and error section.
5) Add `tests/test_response_model_coverage.py` to introspect FastAPI routes and ensure response models exist.
6) Add `tests/test_contract_smoke.py` using `TestClient` to hit key routes with OPENAI_OFFLINE=1, validating schema compliance.
7) Run pytest to verify.

## Test plan
- Unit tests: schema coverage + contract smoke tests.
- Integration/smoke tests (if needed): rely on existing offline-friendly fixtures.
- Manual checks (optional): curl a subset of endpoints.

## Security considerations
- New attack surface: none. Schema additions only.
- Data handling: responses already filtered; no new leaks.
- AuthN/AuthZ changes: none.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared for review
