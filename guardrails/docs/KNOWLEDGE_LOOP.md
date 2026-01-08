# Knowledge Loop

The guardrails folder is only useful if new learnings flow back into it. Follow this loop on every project:

## 1. Capture
- When you fix a recurring bug, add a pattern or expand AI rules to prevent it.
- When CI/workflows evolve, document the change (CI guide, SECURITY, architecture).
- Keep notes in the PR description and link to relevant guardrails sections so others know where to look.

## 2. Distill
- Summarize the root cause + fix in 2–3 sentences.
- Identify the guardrail gap (missing rule, outdated pattern, unclear doc).
- Propose the smallest doc/pattern update that would have prevented the issue.

## 3. Apply
- Update the guardrails repo copy alongside the code change when possible.
- Use `scripts/apply_github_templates.sh` to roll out workflow/doc updates to every repo.
- Announce significant guardrail changes in team channels or release notes.

## 4. Review
- Treat guardrail updates like code: open PRs, request reviews, ensure tests/docs stay aligned.
- Revisit docs quarterly to prune stale guidance and highlight what still matters.

## Anti-patterns
- Hoarding knowledge in personal notes.
- Shipping fixes without updating docs/patterns.
- Adding TODOs without owners; assign every follow-up to a real human.
