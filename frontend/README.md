# Frontend (Vite + React)

## Local Development

Use the Vite proxy so the browser always talks to `http://localhost:5173/api/...` and Vite forwards the
request to the backend. This avoids CORS issues and guarantees the Authorization header is preserved.

```bash
cd frontend
npm install
VITE_PROXY_TARGET=https://rag-qa-system-wv95.onrender.com npm run dev
```

Key points:
- Leave `API_BASE` at the default `/api`. The Vercel deploy rewrites `/api/*` to the backend automatically.
- Never point the browser directly at the public Render URL; doing so will trigger CORS.
- Save your demo token in the “Connection / Demo Auth” panel. The token is stored only in
  `localStorage["ragqa_token"]`.
- All network calls go through the `api` module, which automatically injects `Authorization: Bearer <token>` when
  the header is not already present.

### Verifying Authorization
1. Save a demo token in the Connection panel.
2. Open DevTools → Application → Local Storage → `ragqa_token` to confirm it is stored.
3. Upload any file (a text file should trigger a 400 “Only PDF files are supported.”).
4. In DevTools → Network, inspect `POST http://localhost:5173/api/docs/upload` and confirm the
   `Authorization: Bearer ...` header is present.

### Production (Vercel)
No extra configuration is needed; `/api/*` calls continue to be rewritten to the backend, and the same token
storage/headers apply client-side.
