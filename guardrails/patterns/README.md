# Patterns Overview

Use these patterns before writing new code. They encode proven shapes for this stack.

## Directory map
- `patterns/html_css/`: simple markup/styling snippets (forms, modals, typography). Use for marketing or static pages.
- `patterns/nextjs/`: Next.js App Router patterns (RSC data loading, route handlers, server actions, client widgets).
- `patterns/python_fastapi/`: FastAPI routers, services, repositories, dependency wiring, and error handling.

## How to use
1. Pick the closest pattern (frontend/backend) and copy it into your feature branch.
2. Replace placeholders (namespaces, DTOs, schema fields) with feature-specific values.
3. Keep comments explaining why the pattern exists until reviewers confirm it is understood.
4. Update or add patterns when you discover a repeatable fix. Document the scenario + guardrails.

## Anti-patterns
- Creating new abstractions when an existing pattern would work with minor tweaks.
- Copy/pasting without updating naming/tests/docs.
- Leaving TODOs without linking to the work order or follow-up issue.
