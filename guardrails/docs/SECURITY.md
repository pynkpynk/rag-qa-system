# Security Baseline

Security is part of every task. This document captures the minimum expectations for Next.js + FastAPI stacks.

## Secrets & credentials
- Never commit real secrets. Reference GitHub Secrets (e.g., `secrets.API_TOKEN`) or `.env.local` placeholders.
- Rotate credentials regularly and document rotation steps.
- Mask secrets in logs and CI output; prefer structured logging without raw payloads.

## Authentication & authorization
- Centralize auth in middleware (NextAuth, FastAPI dependencies) so handlers stay thin.
- Enforce least privilege—scope tokens to specific actions and data sets.
- Record every user-sensitive action (audit logs) with correlation IDs.

## Data protection
- Validate and sanitize all inputs at the boundary. Reject malformed payloads with typed errors.
- Encode output properly: escape HTML, avoid eval/dynamic code paths.
- Use HTTPS/TLS everywhere; set HSTS and other secure headers where supported.

## Dependency hygiene
- Pin versions via lockfiles (`pnpm-lock.yaml`, `poetry.lock`, etc.).
- Scan dependencies (Dependabot, pip-audit, npm audit). Patch critical CVEs immediately.
- Avoid unmaintained packages; document deprecation plans when replacing core deps.

## Infrastructure
- Separate staging and production secrets/accounts.
- Enable logging/metrics alerts for auth failures, rate-limit trips, anomalous traffic.
- Keep CI tokens scoped to the minimal repositories/permissions required for workflows.

## Incident response
- Triage high-severity security bugs within 24 hours.
- Hotfix branches must include updated tests + guardrail docs explaining the regression.
- Post-mortems should feed into `docs/KNOWLEDGE_LOOP.md` updates.
