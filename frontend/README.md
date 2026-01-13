# Frontend (Next.js)

## Local Development

```bash
cd frontend
npm install
npm run dev
```

- Configure the backend target by setting `RAGQA_BACKEND_BASE_URL` (e.g. `http://127.0.0.1:8000` locally or your Render URL in prod) and, when running in demo mode, `RAGQA_DEMO_TOKEN` so the BFF proxy can inject the right Authorization header. All `/api/*` requests go through the Next.js route handler, which forwards to the backend using those env vars.
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
