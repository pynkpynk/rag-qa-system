# AI_RULES (Global)

This repository is optimized for long-term human maintainability.

## Primary goals
1) Readability: code should be easy to understand for humans.
2) Extensibility: future changes should be easy and localized.

## Hard constraints
- Keep changes small. Prefer minimal files and minimal public API changes.
- Do not introduce new abstractions unless you can justify them with a concrete future change.
- Reuse existing utilities and patterns. Do NOT create near-duplicates.
- No "clever" code. Prefer boring, explicit, standard patterns.
- If something is uncertain, surface the uncertainty (TODO + explanation) rather than guessing.
- Never check in secrets or tokens. Reference GitHub Secrets placeholders instead.

## Merge requirements
- Every change should be merge-ready: lint/format/test steps must pass locally before opening a PR.
- Keep PR descriptions tight (why + how) and call out follow-ups explicitly.
- Block or mark TODOs if acceptance criteria, rollout, or monitoring steps are unclear.

## Testing requirements
- Add/adjust automated tests for each bug fix or new feature, including at least one edge case.
- Document any intentionally untested code paths with rationale in the PR description.
- Prefer fast, deterministic tests. If something is slow/flaky, isolate and flag it.

## Security posture
- Treat all inputs as hostile; validate and sanitize at the API boundary.
- Centralize authn/z checks—no ad-hoc guards buried inside helpers.
- Avoid logging sensitive fields (passwords, tokens, PII). Scrub before logging.
- Use dependency pins and document upgrade steps when touching build/runtime deps.

## Process (required)
1) Scan the codebase for similar patterns; list what you'll reuse.
2) Propose a short plan (5–10 bullets) with contracts/interfaces.
3) Implement the minimal change set.
4) Add/adjust tests for new behavior and edge cases.
5) Cleanup pass: remove duplication, improve naming, reduce surface area.
6) Self-review against: readability, extensibility, edge cases, security.

## Output requirements (when an AI agent proposes changes)
- Provide full contents of modified files (no diffs).
- List modified files and why each changed.
- Explain any new public APIs and how to use them.

## Dependency policy
- Prefer zero new dependencies.
- If adding a dependency is unavoidable:
  - justify with concrete benefits and why existing options are insufficient,
  - keep the scope minimal,
  - document how to remove/replace it.

## Error handling
- Never silently swallow exceptions.
- Separate user-facing errors from developer logs.
- Prefer structured error models and consistent error responses.

## Security baseline
- Treat all external input as untrusted.
- Authentication/authorization must be centralized (no ad-hoc checks sprinkled around).
- Avoid exposing secrets or tokens in logs, responses, or debug endpoints.

## Documentation baseline
- Keep docstrings for public interfaces.
- Update ARCHITECTURE.md when introducing new modules/layers/contracts.
