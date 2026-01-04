## Backend tests
- Recommended (local venv): from `backend/`, `python -m pip install -r requirements.txt`, `python -m pip install -r requirements-dev.txt`, then `python -m pytest -q`.
- Codex installs/tests: switch to the `rag_net` profile first so dependency downloads (e.g., `pytest`, `auth0-fastapi-api`) succeed, then run the same commands.
- Fallback when pytest can’t be installed: `cd backend && python scripts/smoke_chat_debug_gate.py` ensures the retrieval debug gate logic still passes its four-case contract.

## API docs
- Swagger UI: `/api/swagger`
- OpenAPI JSON: `/api/openapi.json`
- ReDoc: `/api/redoc`

## Admin debug token allowlist
- To allow an opaque admin token to enable `retrieval_debug`, compute its SHA256 digest (e.g., `echo -n "$ADMIN_TOKEN" | shasum -a 256 | cut -d' ' -f1`) and set `ADMIN_DEBUG_TOKEN_SHA256_LIST=<digest>` (comma-separated for multiple tokens).
- This unlocks `retrieval_debug` only when `debug=true` and the global flag is enabled; it does **not** expand document/data access.
- When `debug=true` and the feature flag is enabled, error responses (e.g., `run not found`) now include `debug_meta` so you can diagnose why `retrieval_debug` was excluded; `retrieval_debug` itself remains admin-only and sanitized.

## Local dev workflow (deterministic)
1. Copy `backend/.env.example` to `backend/.env.local`, fill in required keys, and quote any values containing `|` (e.g., `DEV_SUB="auth0|local-user"`). In dev mode, only `DEV_ADMIN_SUBS` grants admin rights; leave it empty to stay non-admin by default.
2. Verify the environment with `python backend/scripts/dev_env_status.py` (all required keys should show `SET`).
3. Start the API via `backend/scripts/dev_up.sh`. The script sources `.env.local`, prefers `backend/.venv/bin/python`, exports deterministic feature flags, and records the uvicorn PID so only one dev server runs on `127.0.0.1:8000`.
4. Seed a deterministic run with `python backend/scripts/dev_seed_run.py` (last line is the `run_id`). Re-run whenever you need a fresh run tied to `DEV_SUB`.
5. Exercise the API: e.g., `curl -s -X POST http://127.0.0.1:8000/api/chat/ask -H 'Content-Type: application/json' -d '{"question":"Ping?","run_id":"<RUN_ID>","debug":true}'`. Non-admin requests will show `debug_meta` (booleans only) but **never** `retrieval_debug`. Admins (via `DEV_ADMIN_SUBS` or token hash) must still pass the global flag + `debug=true` gate, and empty/missing bearer headers never grant admin.
6. Run `python backend/scripts/smoke_chat_debug_gate.py` and (if `pytest` is installed) `python -m pytest -q backend/tests/test_chat_guardrails.py` to verify guardrails.
7. Stop the dev server with `backend/scripts/dev_down.sh`, which reads the stored PID and terminates only the matching uvicorn/watchfiles process. Restart after any `.env.local` edits because `uvicorn --reload` does not reload env vars automatically.
