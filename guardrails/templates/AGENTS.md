# AI Agent Instructions (Repository Root Template)

## Read order
1. `guardrails/docs/AI_RULES.md`
2. Stack-specific rules:
   - `guardrails/docs/AI_RULES.python_fastapi.md`
   - `guardrails/docs/AI_RULES.nextjs.md`
3. `guardrails/docs/ARCHITECTURE.md`
4. `guardrails/patterns/README.md` + relevant pattern folders

## Non‑negotiables
- Keep PRs merge-ready: lint/type/test locally before posting.
- No secrets or tokens in code, logs, or docs. Use GitHub Secrets placeholders.
- Add/adjust tests for every new behavior and edge case.
- Provide full file contents for any modifications in your response.

## Workflow
1. Create a short plan (5–10 bullets) before coding unless the change is trivial.
2. Reuse existing utilities/patterns; document why if you must diverge.
3. Prefer boring, explicit solutions. Highlight uncertainties instead of guessing.
4. Update guardrails docs/patterns when you find new learnings.

## Stack focus
- **Frontend:** Next.js App Router (RSC-first, typed route handlers + server actions).
- **Backend:** FastAPI with dependency-injected services and Pydantic schemas.
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) plus AI PR review via `ai_pr_review_pr_agent.yml`.

## PR expectations
- Fill out `.github/pull_request_template.md`.
- Link to tests, screenshots, or logs proving correctness.
- Surface follow-up work with TODOs + owners.
