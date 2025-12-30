# Architecture Overview

## High-level
This system is composed of:
- Backend: Python / FastAPI (API + services + repositories/infra)
- Frontend: Next.js (server-first rendering, client components only when needed)

## Design principles
- Readability and extensibility over cleverness.
- Clear boundaries:
  - API boundary validates, authorizes, and maps errors.
  - Service layer contains business logic.
  - Repo/Infra handles persistence and external integrations.
- Small change sets, strong tests, consistent patterns.

## Backend layout (recommended)
- app/api/: routers and API boundary
- app/core/: settings, logging, shared primitives
- app/services/: business logic
- app/repositories/: database access
- app/models/: ORM models (if used)
- app/schemas/: Pydantic models (request/response)
- tests/: pytest tests

## Frontend layout (recommended)
- app/: routes, layouts, error/loading boundaries
- components/: reusable UI components
- lib/: fetchers, shared utilities
- styles/: shared tokens/utilities

## Cross-cutting concerns
- Error format: standardized error shape
- AuthN/AuthZ: centralized dependencies/guards
- Logging: boundary logging + no secrets
- Testing: edge cases + regression coverage

## Key contracts
- Backend API response shapes should be versionable and documented.
- Frontend uses a single fetch wrapper for consistent errors.

## When to update this doc
- New module/layer added
- Public API contract changes
- New cross-cutting concern introduced (auth, caching, etc.)
