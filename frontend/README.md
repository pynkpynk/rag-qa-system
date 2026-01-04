# Frontend (Next.js)

## Local Development

```bash
cd frontend
npm install
npm run dev
```

- The dev server listens on `http://localhost:3000`. Requests to `/api/*` are proxied to `http://127.0.0.1:8000/api/*`
  automatically (only in `next dev`; production uses the Vercel rewrite).
- Set `NEXT_PUBLIC_API_BASE` in `.env.local` if you need a non-default API origin.

## Production (Vercel)

`vercel.json` already rewrites `/api/:path*` to the Render backend, so the deployed Next app
continues to call `/api/*` without any extra configuration.
