# Frontend (Next.js)

## Local Development

```bash
cd frontend
npm install
npm run dev
```

- Configure the backend target by setting `RAGQA_BACKEND_BASE_URL` (e.g. `http://127.0.0.1:8000` locally or your Render URL in prod). For local development with `AUTH_MODE=dev`, set `RAGQA_DEV_TOKEN` (defaults to `dev-token`) and leave `RAGQA_INJECT_DEMO_TOKEN=0` so the proxy injects a dev token only when `x-dev-sub` is present. For demo deployments, configure `RAGQA_DEMO_TOKEN` and set `RAGQA_INJECT_DEMO_TOKEN=1` so the proxy injects the demo token when no Authorization header is provided. All `/api/*` requests go through the Next.js route handler, which forwards to the backend using those env vars.
- Local dev tools store the dev subject header in `localStorage` key `ragqa.ui.devSub` (default `dev|user`). Delete or update that key to change the injected `x-dev-sub`.
- `/dev` and `/admin/dev` are blocked when `NODE_ENV=production` unless you set `ALLOW_DEV_ROUTES=1`. When enabled, middleware rewrites `/admin/dev` to `/dev`, so the dev tools become publicly reachable unless another auth layer blocks them—toggle the env only for short, controlled debugging sessions. Even when enabled in production, `/dev` requires an Auth0 session with admin privileges.
- The `/admin` console includes a token settings panel that writes the Bearer token to both `ragqa_token` and `ragqa.ui.token` in `localStorage`.
- When Auth0 is configured, `/chat` and `/runs` require a valid session; unauthenticated visits are redirected to `/auth/login` with a safe `returnTo` so users land back on the page they asked for after logging in.

## Production (Vercel)

`/api/:path*` is handled entirely by the Next.js App Router BFF proxy. Make sure the Vercel deployment has `RAGQA_BACKEND_BASE_URL` and, for demo deployments, `RAGQA_DEMO_TOKEN` configured so the proxy can reach the Render backend.

## Demo Console Quickstart
1. Paste a demo token in the “Demo Token” section and click Save.
2. Fetch docs to see your existing uploads; delete or select them as needed.
3. Upload a PDF (optionally auto-attach it to a selected run).
4. Select docs or runs, then ask a question. Inspect citations and use the chunk drilldown to view excerpts.
5. Manage runs (create/delete, attach docs) and refresh their details.
6. Use Search with your query to find relevant chunks quickly.

## Smoke Tests
Use `frontend/scripts/smoke_bff_proxy_contract.sh` to exercise the proxy/preview/upload/delete contract (see `docs/contracts/bff_proxy_auth.md`). Example:

```bash
WEB_BASE=http://127.0.0.1:3000 DEV_SUB="dev|user" ./frontend/scripts/smoke_bff_proxy_contract.sh
```

The script relies on `curl` and `python3`, uploads a small extractable PDF, verifies auth injection (with and without `x-dev-sub`), and confirms DELETE returns 204 without JSON.
