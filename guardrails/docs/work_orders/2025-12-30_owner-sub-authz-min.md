# Work Order Template

## Title
Enforce owner_sub authorization on documents API

## Goal
What user-visible behavior or capability will be added/changed?

- Guarantee that document list/detail/delete/presign endpoints only operate on resources owned by the authenticated principal (owner_sub match).
- Provide a single dependency that resolves the current user across dev/auth0 modes so routers can consistently fetch the principal.
- Document the access-control contract and add tests that prove non-owners receive 404 responses while authenticated owners can act normally.

## Non-goals
What will NOT be changed in this work order?

- No behavioral changes to runs or chat endpoints (except optional docstring updates); run authorization is already enforced by `ensure_run_access`.
- No new authentication mechanisms or token formats.
- No changes to debug/internal endpoints or smoke routes.
- No new persistence logic or schema migrations.

## Context
- Current behavior:
  - Some document endpoints rely on `_get_doc_for_read`, but list/delete rely on the same helper indirectly and there is no explicit contract/test coverage.
  - Tests do not assert cross-tenant visibility, so regressions could expose other users' docs via list/delete or S3 presign.
- Problem:
  - Without explicit dependency + tests, owner_sub filtering risks regressions when refactoring queries or when S3 presign logic is touched.
- Why now:
  - Contract freeze requires authz guarantees documented and enforced before release.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: owner_sub filtering enforced for list/detail/delete/download/view/reindex; non-owners receive 404.
- [ ] Edge cases covered: unauthenticated requests in Auth0 mode return 401; non-owner deletes return 404; S3 presign guards.
- [ ] Tests added/updated: new contract tests verifying multi-tenant list/delete semantics and 401 behavior.
- [ ] No unnecessary abstraction: reuse existing `_get_doc_for_read` helpers; only add a single dependency for user resolution.
- [ ] No duplicate utilities introduced: rely on guardrail patterns for dependencies/tests.
- [ ] Docs updated if public interfaces changed: `docs/api_contract.md` notes owner_sub and 401/403/404 semantics.

## Constraints / Budgets
- Max modified files: 8
- Max new public APIs: 1 (current_user dependency)
- Dependency additions: forbidden

## Design notes (contracts/interfaces)
- Inputs:
  - `GET /api/docs`, `/api/docs/{id}`, `/api/docs/{id}/download|view`, `/api/docs/{id}/reindex`, `/api/docs/{id}` (DELETE).
- Outputs:
  - Existing response models (DocListItem, DocDetailResponse, DocUploadResponse) remain unchanged; only auth failures return error payloads.
- Error cases:
  - Non-owner: 404 `NOT_FOUND` to hide existence.
  - Unauth in Auth0 mode: 401 `HTTP_ERROR` (missing bearer token).
- Authorization rules:
  - owner_sub must match `Principal.sub` unless caller is admin; `require_permissions` still enforces scopes (read/write/delete).

## Implementation plan (5–10 bullets)
1) Create `get_current_user` dependency in `app.core.authz` that returns the current `Principal` via `get_principal`.
2) Update document routes to depend on `get_current_user` and ensure every list/detail/delete/presign path filters by `owner_sub` (non-admin) using `_get_doc_for_read` and per-query filters.
3) Ensure S3 presign helpers (`download`, `view`, `reindex`) are guarded by `_get_doc_for_read` before issuing URLs.
4) Update `docs/api_contract.md` to mention owner-based access, 401 on auth failures, and 404 hiding semantics.
5) Add `tests/test_docs_owner_authz.py` using FastAPI TestClient with a temporary SQLite session override to simulate different principals via `x-dev-sub` headers.
6) Tests: verify owner can list/delete, other users see empty list/404, and auth0 mode without Authorization header returns 401.
7) Confirm `pytest -q` passes locally (uses OPENAI_OFFLINE=1) and no new dependencies introduced.

## Test plan
- Unit tests:
  - `tests/test_docs_owner_authz.py` covering list/delete visibility and auth mode 401.
- Integration/smoke tests:
  - Existing backend smoke indirectly exercises owner filters.
- Manual checks (optional):
  - Hit `/api/docs` in dev with different `x-dev-sub` headers to confirm filtering.

## Security considerations
- New attack surface:
  - None; we are restricting access further.
- Data handling:
  - Ensures S3 presign URLs only generated for owned documents.
- AuthN/AuthZ changes:
  - Adds explicit dependency for retrieving the principal; permission checks remain in place.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared for review
