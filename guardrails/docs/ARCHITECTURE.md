# Architecture Overview

## Reference stack
- **Frontend:** Next.js (App Router, Server Components first, TypeScript enforced)
- **Backend:** FastAPI (typed routers, dependency-injected services, SQL/NoSQL repos)
- **CI/CD:** GitHub Actions running lint/type/test + AI PR review

## Deployment topology
```
[Browser]
   ↓ (HTTPS)
[Next.js Edge/Node runtime] ↔ [FastAPI app] ↔ [DB/cache/queues]
```
- Next.js handles routing, server actions, and static asset delivery.
- FastAPI exposes REST endpoints consumed by Next.js and third parties.
- Shared contracts (OpenAPI schemas / TypeScript types) keep both sides aligned.

## Frontend layout
- `app/`: routes, layouts, loading/error boundaries, server actions, route handlers.
- `components/`: client/server components; keep pure UI separate from data fetching.
- `lib/`: fetch wrappers, auth helpers, utility functions.
- `styles/`: global tokens, CSS Modules, Tailwind config (match project setup).

### Frontend principles
- Server-first rendering; client components only for interactivity.
- Typed fetch wrapper that encodes error handling, auth headers, and base URLs.
- Shared `UiError` and `SuccessResult` DTOs across components for consistent UX.

## Backend layout
- `app/api`: routers grouped by domain; each router validates, authorizes, and maps errors.
- `app/services`: business logic orchestrators; pure functions when possible.
- `app/repositories`: persistence and external integrations (DB, cache, APIs).
- `app/core`: settings, logging, security, dependency wiring.
- `app/schemas`: Pydantic models for request/response payloads.
- `tests`: pytest suites mirroring modules (unit + integration).

### Backend principles
- Dependency injection via FastAPI `Depends` to keep handlers thin and testable.
- Explicit error models (e.g., `ApiError`) returned to frontends; map internal exceptions once.
- Security baked in: auth dependencies, rate limiting, audit logging as required.

## Shared contracts
- Define DTOs once (e.g., generate TypeScript types from OpenAPI or share schema definitions).
- Align enum/string literal values between frontend and backend.
- Document API versioning strategy; prefer additive changes + feature flags over breaking releases.

## Observability
- Structured logs with correlation IDs passed between Next.js and FastAPI.
- Metrics for request latency, error rates, cache hit ratio.
- Trace critical flows (auth, payments, data writes) across services.

## Testing strategy
- Frontend: unit tests for utilities/components, end-to-end tests for key journeys.
- Backend: unit tests for services, integration tests hitting FastAPI routers, contract tests vs mock clients.
- CI gates must run formatting, linting, typing, tests on every PR.

## When to update this doc
- New subsystems (queues, background workers, feature flags) added.
- Contracts between frontend/backend change materially.
- Deployment topology, CI steps, or observability tooling shifts.
