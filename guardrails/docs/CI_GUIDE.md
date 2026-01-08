# CI Guide

This repo template expects GitHub Actions for every PR + main branch push. The CI workflow lives in `templates/github/workflows/ci_template.yml`.

## Required jobs
1. **Setup:** checkout repo, enable `actions/cache` for Node + Python deps, and pin tool versions (Node 20, Python 3.11).
2. **Frontend (Next.js App Router):**
   - Install dependencies (`pnpm install` or project-equivalent).
   - Run `pnpm lint`, `pnpm test`, and (optionally) `pnpm typecheck`.
   - Build with `pnpm build` to ensure server/client bundles compile.
3. **Backend (FastAPI):**
   - Install via `pip install -r requirements.txt` (or `pip install -e .[dev]`).
   - Run `ruff`/`black --check` or the project's linters.
   - Run `pytest` with coverage; fail fast when coverage drops.
4. **AI PR Review (optional but recommended):** triggered on PR events by `ai_pr_review_pr_agent.yml`. Requires repo/organization secret `PR_AGENT_GITHUB_TOKEN`.

## Patterns
- All commands must be deterministic; fail on warnings.
- When caching, bust the cache when lockfiles change (`pnpm-lock.yaml`, `poetry.lock`, etc.).
- Upload artifacts (coverage, junit) when available so reviewers can inspect failures.
- Keep job runtimes under 10 minutes; split into parallel jobs if needed.

## Adding new checks
1. Update `docs/AI_RULES.md` or relevant pattern docs if the new check enforces a policy.
2. Modify the workflow template and re-run `scripts/apply_github_templates.sh --force` to propagate changes.
3. Document new environment variables or secrets in README/SECURITY to avoid tribal knowledge.
