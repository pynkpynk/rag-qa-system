# Work Order Template

## Title
Security/Ops hardening v1 (MVP minimum)

## Goal
Ensure production defaults are safe: debug data never emits in prod, uploads are validated, logs remain secret-free, and owner authorization is tested.

## Non-goals
- No new endpoints or business features.
- No dependency additions.

## Context
- Current behavior: prod can enable OPENAI_OFFLINE/debug meta; uploads rely on loose checks; logs may include sensitive headers; owner auth tests are minimal.
- Problem: insecure defaults can leak data or allow misconfiguration.
- Why now: approaching MVP, need automated guards.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: chat debug fields suppressed when APP_ENV=prod; debug routes gated to non-prod.
- [ ] Upload validation: rejects non-PDF/oversized files with correct status codes.
- [ ] Tests added/updated for debug gating, uploads, owner auth.
- [ ] No new abstractions; reuse existing helpers.
- [ ] No duplicate utilities or dependencies.
- [ ] Work order reflected in docs/tests.

## Constraints / Budgets
- Max modified files: 12
- Max new public APIs: 0
- Dependency additions: forbidden

## Design notes (contracts/interfaces)
- Inputs: env vars (APP_ENV, AUTH_MODE), HTTP requests via docs/chat endpoints.
- Outputs: same JSON schema; debug fields removed when prod.
- Error cases: consistent HTTP 4xx with standard error payload.
- Auth rules: owner_sub enforcement remains.

## Implementation plan (5–10 bullets)
1) Extend Settings/auth to enforce APP_ENV, dev tokens only in dev (already partially done).
2) Gate chat debug_meta/retrieval_debug behind AUTH_MODE==dev; block /api/_debug routes in prod.
3) Introduce MAX_UPLOAD_BYTES from Settings; ensure upload checks content-type, PDF header, size.
4) Add tests for upload violations (415/413/422 style).
5) Add tests verifying prod-mode chat responses lack debug fields and debug routes are inaccessible.
6) Ensure owner auth tests cover list/detail/delete cross-tenant behavior.
7) Run pytest -q and optional scripts.

## Test plan
- Unit tests: new upload, chat debug gating, owner auth tests.
- Integration: rely on TestClient offline mode.
- Manual: optional smoke for prod env.

## Security considerations
- No new attack surface; reduces leak risk.
- Logs remain metadata-only.
- Dev headers blocked in prod.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared
