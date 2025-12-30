# Work Order Template

## Title
Deliver MVP UI skeleton for docs + chat flows

## Goal
What user-visible behavior or capability will be added/changed?

- Provide a minimal Next.js UI that surfaces document management (list/upload/delete) and the chat/ask experience with citations.
- Ensure the frontend communicates with the existing backend contract, wiring auth headers (Bearer + optional x-dev-sub) consistently.
- Offer a simple PDF viewer page that links from chat citations to a document page.

## Non-goals
What will NOT be changed in this work order?

- No styling polish beyond basic layout (focus on functionality).
- No real authentication provider integration (use existing token/header inputs).
- No new backend endpoints or schema changes.

## Context
- Current behavior:
  - Frontend lacks a unified page for document CRUD and chat interactions.
  - Manual API calls are used for testing; citations can’t be clicked to view PDFs.
- Problem:
  - Without a UI skeleton, manual QA and demos are blocked.
- Why now:
  - Contract freeze requires a UI that exercises the documented endpoints before release.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: docs list shows owner documents; upload and delete call backend endpoints; ask form submits and renders answer + citations.
- [ ] Edge cases covered: 401 responses show “not authenticated”; deleting non-owned doc shows “not found / not owned”.
- [ ] Tests added/updated: minimal type-safe API client (no automated tests required for UI skeleton per scope).
- [ ] No unnecessary abstraction: single API client module reused by pages/components.
- [ ] No duplicate utilities introduced: follow guardrails patterns for API fetching.
- [ ] Docs updated if public interfaces changed: not required (contract already documented).

## Constraints / Budgets
- Max modified files: 10
- Max new public APIs: 0 (frontend only)
- Dependency additions: none

## Design notes (contracts/interfaces)
- Inputs:
  - Docs API: `/api/docs`, `/api/docs/upload`, `/api/docs/{id}`
  - Chat API: `/api/chat/ask`
  - View PDF: `/api/docs/{id}/view`
- Outputs:
  - Use existing response schemas documented in docs/api_contract.md.
- Error cases:
  - 401 -> show banner
  - 404 -> show inline message near doc row
- Authorization rules:
  - Token header `Authorization: Bearer ...`
  - Optional `x-dev-sub` for multi-tenant dev testing (configurable input)

## Implementation plan (5–10 bullets)
1) Create shared API client utility (`frontend/lib/api.ts`) that pulls base URL + headers from env/user input and centralizes fetch + error handling.
2) Build Docs page with list + upload form + delete buttons using SWR or basic state (no extra deps).
3) Build Chat page with question textarea, run selection (optional), debug toggle, and response rendering including citations.
4) When rendering citations, link to `/pdf-viewer?docId=X&page=Y`.
5) Add `/pdf-viewer` route that loads `/api/docs/{id}/view` (presigned) inside an iframe and anchors to page.
6) Provide top-level layout/nav between Docs and Chat pages.
7) Surface error states (401/404) via API client responses.
8) Wire optional dev headers (x-dev-sub) via global form or local storage.

## Test plan
- Manual:
  - Run `npm run dev`, verify docs list, upload, delete, ask, and citation links.
  - Force 401 by switching to auth0 mode or removing token, ensure banner renders.
- Automated:
  - Not required for MVP skeleton per scope (manual verification only).

## Security considerations
- New attack surface:
  - UI exposes token/sub inputs; ensure they’re not logged.
- Data handling:
  - Avoid storing tokens beyond local state/session storage.
- AuthN/AuthZ changes:
  - None; frontend simply forwards headers to backend.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared for review
