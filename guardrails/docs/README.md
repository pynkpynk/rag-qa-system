# Patterns

These patterns are the "approved" shapes for this repo.
Keep this folder small. Add a new pattern only when it prevents repeated mistakes.

## Backend (Python/FastAPI)
- router.py: thin endpoints
- dependencies.py: DI for DB/session/auth
- schemas.py: request/response models
- service.py: business logic
- repository.py: persistence access
- errors.py: standardized error format
- test_example.py: minimal pytest style

## Frontend (Next.js)
- component.server.tsx: server component baseline
- component.client.tsx: client component baseline
- fetcher.ts: typed fetch wrapper with consistent errors
- route.ts: route handler example (if needed)
- error.tsx / loading.tsx: boundaries
- styles.module.css: CSS Modules baseline

## HTML/CSS
- semantic_layout.html: semantic + accessible baseline
- base.css: minimal baseline
