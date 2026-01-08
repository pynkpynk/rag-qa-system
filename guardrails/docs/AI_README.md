# Guardrails (Read First)

This folder is the repository's "operating system" for AI-assisted coding.
Primary goals: readability and extensibility.

## Read order (required)
1) docs/AI_RULES.md
2) docs/AI_RULES.python_fastapi.md (backend work)
3) docs/AI_RULES.nextjs.md (frontend work)
4) patterns/README.md + relevant patterns (each pattern describes when/why to use it)
5) docs/ARCHITECTURE.md, docs/SECURITY.md, docs/PR_REVIEW_GUIDELINES.md, docs/CI_GUIDE.md

## Non-negotiables
- Keep changes small. Minimal files, minimal public API changes.
- No new abstractions unless justified by a concrete future change.
- Reuse existing utilities; do NOT create near-duplicates.
- Follow patterns in `patterns/` (approved shapes).
- Provide full contents of modified files (no diffs).
- Add/update tests for new behavior + at least one edge case.

## How to use patterns
- Before writing code, find the closest pattern and adapt it.
- If no pattern exists, propose a new pattern only if it will prevent repeated mistakes.
- `patterns/README.md` explains what each pattern covers and how to apply it safely.

## Tooling (quality gates)
- Format/Lint/Type/Test must pass locally and in CI.
- Do not disable gates to "make it pass". Fix the root cause.
