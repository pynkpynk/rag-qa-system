# AI_RULES (Next.js / HTML / CSS)

These rules assume Next.js App Router with React Server Components (RSC) first.

## Rendering model
- Default to Server Components; only mark `"use client"` when browser APIs or hooks are required.
- Keep Client Components leaf-level; lift data fetching + mutations to Server Components when possible.
- Co-locate loading/error boundaries with routes to prevent cascading failures.

## Server Actions vs Route Handlers
### Use Server Actions when
- The mutation is tightly coupled to a page/segment (forms, buttons, inline workflows).
- You need automatic access to cookies/session without wiring fetch/auth headers.
- The operation is not intended for public API consumers.

### Use Route Handlers when
- The capability must be callable by other clients (mobile apps, services, webhooks).
- You need control over HTTP semantics (cache headers, streaming, content negotiation).
- Sharing logic between Next.js and FastAPI is required—keep contracts aligned.

### Hard rules
- Never expose the same capability through both routes and actions without documenting why.
- Route handlers must return typed responses (`NextResponse.json<MyDto>`). Never return `any`.
- Use shared schema definitions (e.g., Zod or TypeScript types) for responses to avoid drift.

## Data fetching
- Wrap `fetch` in a typed helper to set base URL, headers, retries, and error normalization.
- Use React cache/revalidate settings intentionally—set `revalidate`/`cache` explicitly.
- Cross-origin calls go through FastAPI unless there is a documented exception.

## Error handling
- Convert thrown errors into a shared `UiError` object with `code/title/message`.
- Error boundaries should render the same `ErrorNotice` component everywhere.
- Never show stack traces or raw API payloads to users; log via structured server logs instead.

## Route handlers
- Keep handlers thin: validate input, call a service, map the response, set headers.
- Always set `Content-Type` and status codes; default to 200/201 for success, 4xx/5xx otherwise.
- Authenticate using middleware/handlers (NextAuth, custom) instead of inline ad-hoc checks.

## Server actions
- Mark every action `"use server"` and keep them side-effect free except for the intended mutation.
- Validate inputs using shared schemas before invoking services.
- Return typed DTOs or redirect; no implicit `any`.

## Conventions
- Type everything: components, props, hooks, route handlers, server actions.
- Separate UI composition (`components/`) from data utilities (`lib/`).
- Prefer semantic HTML and accessible patterns (labels, aria attributes, keyboard support).

## Styling
- Use CSS Modules, Tailwind, or the project's approved system consistently.
- Avoid inline styles; prefer tokens/variables for spacing/color.
- Keep responsive rules simple; leverage CSS logical properties when possible.

## What NOT to do
- Do not mix client/server behaviors within the same file unless required.
- Do not duplicate fetch logic; extend the shared helper.
- Do not leave TODOs without context or owner/date.
