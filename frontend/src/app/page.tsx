"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  app: string;
  app_env: string;
  auth_mode: string;
  git_sha: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    fetch(`${API_BASE}/health`)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return (await res.json()) as HealthResponse;
      })
      .then((data) => {
        if (mounted) {
          setHealth(data);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (mounted) {
          setError(err.message || "Failed to fetch health");
          setHealth(null);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <main>
      <h1>RAG QA System</h1>
      <p>
        API base: <code>{API_BASE}</code>
      </p>
      {health ? (
        <section>
          <h2>Backend Health</h2>
          <ul>
            <li>Status: {health.status}</li>
            <li>Environment: {health.app_env}</li>
            <li>Auth mode: {health.auth_mode}</li>
            <li>Git SHA: {health.git_sha}</li>
          </ul>
        </section>
      ) : (
        <p>Loading health…</p>
      )}
      {error && (
        <p>
          <strong>Error:</strong> {error}
        </p>
      )}
      <section>
        <h2>Docs</h2>
        <ul>
          <li>
            <a href="/api/swagger" target="_blank" rel="noreferrer">
              Swagger UI
            </a>
          </li>
          <li>
            <a href="/api/redoc" target="_blank" rel="noreferrer">
              ReDoc
            </a>
          </li>
          <li>
            <a href="/api/openapi.json" target="_blank" rel="noreferrer">
              OpenAPI JSON
            </a>
          </li>
        </ul>
      </section>
    </main>
  );
}
