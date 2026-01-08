# PR Review Guidelines

These guardrails assume mixed human + AI reviews. Every review must keep readability, extensibility, and safety at A+ quality.

## Before reviewing
- Confirm CI status. If failing or missing, request fixes before deep review.
- Read the PR description + linked issues. Make sure scope is clear and tests are listed.
- Skim the diff to understand the architecture impact before drilling into details.

## What to look for
- **Correctness:** Business logic matches requirements, covers edge cases, no silent failure paths.
- **Tests:** New behavior has direct tests (unit/integration/e2e). Verify meaningful assertions, not just snapshots.
- **Security & privacy:** Inputs validated, secrets excluded from logs/config, authz checks enforced in one place.
- **Performance:** Hot paths stay O(1) per request; avoid unnecessary loops, large payloads, or blocking calls on the main thread.
- **Dependencies:** No new deps unless justified. Versions pinned and documented.
- **Docs:** ARCHITECTURE/AI_RULES updated when contracts change; PR template checklist filled in.

## Review workflow
1. Leave blocking comments when the issue must be fixed before merge (use `Blocking:` prefix).
2. Leave non-blocking suggestions for polish/cleanup; clearly tag them as optional.
3. Summarize the state: `Approved`, `Approved with nits`, or `Changes requested`.
4. If unsure, explicitly ask for clarification instead of guessing. Link to TODOs/work orders if follow-ups are needed.

## AI reviewer requirements
- Never invent behavior. Base comments on the diff + repo history.
- Quote relevant code blocks so humans can verify quickly.
- Suggest concrete fixes or tests; avoid vague statements.
- Post comments via workflow bots (see `templates/github/workflows/ai_pr_review_pr_agent.yml`).

## Merge blockers
- Missing/incorrect tests.
- Undocumented API or contract changes.
- Security regressions (data leaks, auth bypass, injection vectors).
- Unresolved TODOs in scope without owners.
