# AI_RULES (Next.js / HTML / CSS)

## Goals
- Readable components with clear responsibilities.
- Extensible UI architecture: adding new features should be localized.

## Rendering model
- Prefer Server Components by default (App Router assumed).
- Use Client Components only when needed (state, effects, browser APIs).

## Server Actions vs Route Handlers (decision rules)
### Prefer Server Actions when:
- The call is tightly coupled to a page/component (form submit, UI-triggered mutation).
- You want to keep business logic server-side without exposing a public HTTP API surface.
- You want simpler auth via server context (cookies/session) and avoid extra client fetch plumbing.

### Prefer Route Handlers when:
- You need a stable HTTP API boundary (mobile clients, external integrations, webhooks).
- You want clear HTTP semantics (caching headers, status codes, content negotiation).
- You need a public interface that other systems can call.

### Hard rule
- Do not mix both for the same capability unless there is a clear reason (document it).

## Data fetching
- Use a single typed fetch wrapper for client/server fetch calls.
- Normalize error handling across UI: convert all errors into a shared `UiError` shape.

## Error handling (UI)
- Always map unknown errors to a safe user message (never show raw stack traces).
- Prefer a single error display component (e.g., `ErrorNotice`) across pages/components.
- Keep error presentation consistent (title/message/code).

## Conventions
- Use TypeScript if the repo is TS. If JS-only, mirror typing via JSDoc.
- Keep components small. Separate data fetching, UI rendering, and formatting.
- Prefer semantic HTML and accessibility (labels, aria where needed).
- Avoid inline styles; use CSS Modules (or existing styling system already in repo).

## CSS
- Prefer CSS Modules for component-local styles.
- Keep class names meaningful; avoid deeply nested selectors.
- Avoid magic numbers; use CSS variables/tokens when shared.

## What NOT to do
- No huge components mixing data fetching + heavy UI + state + side effects.
- No duplicated fetch logic scattered across components.
- No "temporary" hacks without a follow-up note (TODO with reason).
