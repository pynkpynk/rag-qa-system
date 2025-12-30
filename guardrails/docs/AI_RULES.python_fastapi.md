# AI_RULES (Python / FastAPI)

## Objectives
- Optimize for human readability and extensibility.
- Keep security rules consistent and centralized.

## Architecture: layering and boundaries
- API layer: FastAPI routers, request/response models, auth dependencies.
- Service layer: business logic (pure-ish), no FastAPI objects.
- Repository/Infra: database, external services, S3, HTTP clients, etc.
- Dependency direction: API -> Service -> Repo/Infra only (no reverse deps).

## Conventions
- Use Pydantic models for request/response boundaries.
- Avoid returning ORM objects directly from API.
- Prefer explicit types (mypy-friendly style).
- Keep functions small; prefer clear naming over comments.

## AuthN/AuthZ (required)
### AuthN (authentication)
- `get_current_user` verifies credentials (e.g., JWT) and returns a `CurrentUser` object.
- AuthN must be centralized. No ad-hoc parsing in endpoints.

### AuthZ (authorization)
- Use dependencies like `require_scope(...)` for capability checks (scopes/roles).
- For resource authorization, keep the logic consistent:
  - If the client should not learn whether a resource exists, return **404** for both "not found" and "not allowed".
  - Use **403** only when it is acceptable to reveal existence, but the action is forbidden (e.g., admin screens, internal tooling).
- Always document which endpoints use "hide existence" semantics.

## Routers
- Each router module owns one "resource" (e.g., documents, users).
- Each endpoint should be thin:
  - validate + authorize + call service + map to response.

## Dependencies (DI)
- Create dedicated dependency providers (e.g., get_db, get_uow, get_current_user).
- Do not access globals directly inside endpoints.
- Auth + authorization checks must be dependencies or service-level guards (consistent placement).

## DB session + Unit of Work (required when using a DB)
- Use a Unit of Work (UoW) pattern to handle:
  - session lifetime
  - commit/rollback behavior
  - repository wiring
- Services should not manually commit/rollback.
- Repositories should receive the session from UoW or DI, never create sessions.

## DTO mapping (ORM ↔ Pydantic)
- Keep mapping logic explicit and centralized.
- Prefer `PydanticModel.model_validate(orm_obj, from_attributes=True)` (Pydantic v2) or dedicated mapping functions.
- Do not leak ORM objects outside repo/service boundaries.

## Error handling
- Use a consistent error response format.
- Never silently swallow exceptions.
- Do not leak internal exceptions to clients.
- Map domain errors -> HTTP errors at API boundary.

## Testing
- Prefer unit tests for services/repositories.
- Add edge-case tests (empty input, invalid, unauthorized, not found).
- Keep tests deterministic; avoid network calls in unit tests.

## Logging
- Never log secrets/tokens.
- Log at boundaries: request start/end, service failures, external calls failures.

## What NOT to do
- No giant "utils.py" dumping ground.
- No god objects (service does everything).
- No implicit global state (except configuration).
