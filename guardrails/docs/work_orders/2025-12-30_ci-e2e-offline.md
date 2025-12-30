# Work Order Template

## Title
CI E2E stability + offline retrieval

## Goal
Ensure backend/scripts/ci_e2e_gate.sh works with configurable ports on dev/CI machines and that OPENAI_OFFLINE mode still returns meaningful answers/citations so the gate succeeds without external APIs.

## Non-goals
- No changes to production auth logic or new endpoints.
- Do not add new dependencies beyond existing stdlib/bash.

## Context
- Current behavior: ci_e2e gate assumes fixed ports (8010/55432) and fails when Docker Desktop or local services already occupy them. Offline embeddings can yield zero chunks or empty answers, causing validations to fail.
- Problem: The E2E workflow becomes flaky on real developer laptops and GitHub runners, blocking releases.
- Why now: We added the E2E step to CI and need deterministic success across environments before GA.

## Acceptance Criteria (must all pass)
- [ ] Functional behavior: ci_e2e_gate honors RAGQA_CI_API_PORT / RAGQA_CI_DB_PORT, checks port availability early, and logs diagnostics (LOG_FILE/TMP_DIR/request id) on failure.
- [ ] Edge cases: OPENAI_OFFLINE=1 yields non-empty retrieval rows (similarity thresholds disabled) and ask returns citations mentioning Alice/Bob.
- [ ] Tests added/updated: backend test proving offline ask returns citations referencing seeded chunk text.
- [ ] No unnecessary abstraction: reuse existing chat helpers; only minimal conditionals for offline mode.
- [ ] No duplicate utilities introduced: offline fallbacks live in chat route.
- [ ] Docs/scripts updated where relevant (ci_e2e script).

## Constraints / Budgets
- Max modified files: 8
- Max new public APIs: 0
- Dependency additions: forbidden

## Design notes (contracts/interfaces)
- Inputs: bash env vars RAGQA_CI_API_PORT/RAGQA_CI_DB_PORT, FASTAPI `/chat/ask` route when OPENAI_OFFLINE=1.
- Outputs: same JSON schema; offline logic must still satisfy `ChatResponse` contract.
- Error cases: `ci_e2e_gate.sh` must abort with helpful output (request id + log tail).
- Authorization rules: unchanged (dev auth for gate).

## Implementation plan (5–10 bullets)
1) Update ci_e2e_gate.sh to resolve ports from new env vars, guard with lsof, and record diagnostics before exit.
2) Ensure script uses resolved API URL everywhere (curl / host logging) and prints log/tmp paths when exiting.
3) Adjust retrieval (fetch_chunks) to bypass similarity thresholds when `_is_offline()` and ensure fallback chunk selection when rows are empty.
4) Extend `answer_with_contract` (or route-level branch) to produce citations + synthetic answer in offline mode using retrieved chunk text.
5) Add regression test verifying offline ask returns non-empty citations referencing “Stakeholders: Alice, Bob”.
6) Re-run backend pytest + (optionally) ci_e2e_gate locally with alternate ports.

## Test plan
- Unit tests: new offline citation test in backend/tests.
- Integration: run backend/scripts/ci_e2e_gate.sh with overridden ports.
- Manual: optional curl to /chat/ask with OPENAI_OFFLINE=1.

## Security considerations
- New attack surface: none (offline mode already existed).
- Data handling: ensure offline answers still redact sensitive data.
- AuthN/AuthZ: unchanged.

## Definition of Done
- [ ] Acceptance Criteria met
- [ ] Tests pass
- [ ] Lint/format/type checks pass (if configured)
- [ ] Full-file output prepared for review
