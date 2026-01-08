## Backend tests
- Recommended (local venv): from `backend/`, `python -m pip install -r requirements.txt`, `python -m pip install -r requirements-dev.txt`, then `python -m pytest -q`.
- Codex installs/tests: switch to the `rag_net` profile first so dependency downloads (e.g., `pytest`, `auth0-fastapi-api`) succeed, then run the same commands.
- Fallback when pytest can’t be installed: `cd backend && python scripts/smoke_chat_debug_gate.py` ensures the retrieval debug gate logic still passes its four-case contract.

## Preflight
- Run `make preflight` from the repo root to compile backend Python files and execute `pytest backend/tests` with deterministic env vars.
- Optional: `git config core.hooksPath .githooks` enables the provided `pre-push` hook so pushes run `make preflight` automatically.

## API docs
- Swagger UI: `/api/swagger`
- OpenAPI JSON: `/api/openapi.json`
- ReDoc: `/api/redoc`
- `POST /api/search` treats missing `mode` as `library`; set `mode="selected_docs"` and pass `document_ids` to scope to specific documents.

## Admin debug token allowlist
- To allow an opaque admin token to enable `retrieval_debug`, compute its SHA256 digest (e.g., `echo -n "$ADMIN_TOKEN" | shasum -a 256 | cut -d' ' -f1`) and set `ADMIN_DEBUG_TOKEN_SHA256_LIST=<digest>` (comma-separated for multiple tokens).
- This unlocks `retrieval_debug` only when `debug=true` and the global flag is enabled; it does **not** expand document/data access.
- When `debug=true` and the feature flag is enabled, error responses (e.g., `run not found`) now include `debug_meta` so you can diagnose why `retrieval_debug` was excluded; `retrieval_debug` itself remains admin-only and sanitized.

## Production guardrails
- Debug/diagnostic surfaces (retrieval debug, `/api/_debug/*`) are disabled when `APP_ENV=prod` unless you explicitly set `ALLOW_PROD_DEBUG=1`. Keep the default `0` in production and only flip it temporarily with an audit trail.
- CORS is deny-by-default in prod. Set `cors_origin` (comma-separated origins, e.g. `https://app.example.com,https://staging.example.com`) in your environment to whitelist specific frontends; leaving it blank keeps the API private.

## Demo tokens (AUTH_MODE=demo)
- Production deployments using `AUTH_MODE=demo` **must** configure an allowlist: either set `DEMO_TOKEN_SHA256_LIST` (preferred, comma-separated SHA256 digests) or `DEMO_TOKEN_PLAINTEXT` for a single shared token.
- Generate a digest with `echo -n "my-demo-token" | shasum -a 256 | cut -d' ' -f1`, then set `DEMO_TOKEN_SHA256_LIST=<digest>` on Render. You can still use `DEMO_TOKEN_PLAINTEXT` for staging/dev, but hashes are safer in prod.
- Verify access with `curl -H "Authorization: Bearer my-demo-token" https://<host>/api/health`; invalid tokens should return `401 {"error":{"code":"NOT_AUTHENTICATED",...}}`.

## Production smoke test
- Set `API_BASE`, `TOKEN_A`, `TOKEN_B`, and `PDF` (path to a test PDF) in your environment.
- Run `make prod-smoke` (or `bash scripts/prod_smoke.sh`). The script uploads the PDF, validates tenant isolation for docs/runs/chunks, runs an Ask call, and prints PASS/FAIL.
- Example: `API_BASE=https://rag.example.com/api TOKEN_A=... TOKEN_B=... PDF=./sample.pdf make prod-smoke`

## Production smoke (health/search)
- For a quicker API check (no upload), set `API_BASE` (without trailing slash) and `TOKEN`, then run:
  ```bash
  API_BASE=https://rag-qa-system-wv95.onrender.com \
  TOKEN=demo-token \
  make smoke-prod
  ```
- This runs `GET /api/health`, `GET /api/chunks/health`, and `POST /api/search` (with debug flag) and fails fast on any non-2xx response.
- `/api/chunks/health` now reports the live DB revision vs. code head; the smoke script fails if they differ unless you set `SMOKE_ALLOW_ALEMBIC_BEHIND=1` to downgrade the mismatch to a warning (use cautiously).

## Retrieval regression gate
- Deterministic eval cases for `/api/search` live in `backend/tests/fixtures/search_eval_cases.json`.
- Run `make eval-regression` to execute only the regression test (`backend/tests/test_search_regression_eval.py`). This uploads the smoke PDF and ensures search continues returning the expected snippets; CI/preflight also runs it via `pytest backend/tests`.
- The eval regression needs a working Postgres `DATABASE_URL`. If port `5432` is already in use, either point to your existing local Postgres or map the docker container to a different host port:
  - Use existing local Postgres (default port):
    ```bash
    export DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:5432/ragqa_test"
    make eval-regression
    ```
  - Map docker to host port 5433 and pass that URL:
    ```bash
    docker run -p 5433:5432 ... postgres
    export DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:5433/ragqa_test"
    make eval-regression
    ```

## Production DB migration helper
- To upgrade the production DB schema when you have a PSQL URL:
  ```bash
  PSQL_URL="postgresql+psycopg://user:pass@host:5432/db" make migrate-prod
  ```
- The script runs Alembic using `backend/alembic.ini`, prints the current revision, executes `upgrade head`, and prints the revision afterward (without echoing full credentials). Ensure `PSQL_URL` points to the target DB and contains necessary credentials.

## Local dev workflow (deterministic)
1. Copy `backend/.env.example` to `backend/.env.local`, fill in required keys, and quote any values containing `|` (e.g., `DEV_SUB="auth0|local-user"`). In dev mode, only `DEV_ADMIN_SUBS` grants admin rights; leave it empty to stay non-admin by default.
2. Verify the environment with `python backend/scripts/dev_env_status.py` (all required keys should show `SET`).
3. Start the API via `backend/scripts/dev_up.sh`. The script sources `.env.local`, prefers `backend/.venv/bin/python`, exports deterministic feature flags, and records the uvicorn PID so only one dev server runs on `127.0.0.1:8000`.
4. Seed a deterministic run with `python backend/scripts/dev_seed_run.py` (last line is the `run_id`). Re-run whenever you need a fresh run tied to `DEV_SUB`.
5. Exercise the API: e.g., `curl -s -X POST http://127.0.0.1:8000/api/chat/ask -H 'Content-Type: application/json' -d '{"question":"Ping?","run_id":"<RUN_ID>","debug":true}'`. Non-admin requests will show `debug_meta` (booleans only) but **never** `retrieval_debug`. Admins (via `DEV_ADMIN_SUBS` or token hash) must still pass the global flag + `debug=true` gate, and empty/missing bearer headers never grant admin.
6. Run `python backend/scripts/smoke_chat_debug_gate.py` and (if `pytest` is installed) `python -m pytest -q backend/tests/test_chat_guardrails.py` to verify guardrails.
7. Stop the dev server with `backend/scripts/dev_down.sh`, which reads the stored PID and terminates only the matching uvicorn/watchfiles process. Restart after any `.env.local` edits because `uvicorn --reload` does not reload env vars automatically.
