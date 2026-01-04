"use client";

import { useEffect, useMemo, useState } from "react";
import { authFetch } from "../lib/apiClient";
import { clearToken, getToken, setToken } from "../lib/authToken";

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
  const [tokenValue, setTokenValue] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const [docsData, setDocsData] = useState<string | null>(null);
  const [docsError, setDocsError] = useState<string | null>(null);

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
    const stored = getToken();
    if (stored) {
      setTokenValue(stored);
      setHasToken(true);
    }
    return () => {
      mounted = false;
    };
  }, []);

  const tokenStatus = useMemo(() => {
    if (!hasToken) {
      return "No token set";
    }
    const masked =
      tokenValue.length > 6
        ? `${tokenValue.slice(0, 3)}…${tokenValue.slice(-3)}`
        : "•••";
    return `Token set (${masked})`;
  }, [hasToken, tokenValue]);

  const saveToken = () => {
    setToken(tokenValue);
    setHasToken(tokenValue.trim().length > 0);
  };

  const removeToken = () => {
    clearToken();
    setTokenValue("");
    setHasToken(false);
  };

  const fetchDocs = async () => {
    setDocsError(null);
    setDocsData(null);
    try {
      const resp = await authFetch("/docs");
      const body = await resp.text();
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
      }
      setDocsData(body);
    } catch (err) {
      setDocsError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <main>
      <h1>RAG QA System</h1>
      <p>
        API base: <code>{API_BASE}</code>
      </p>
      <section>
        <h2>Demo Token</h2>
        <p>{tokenStatus}</p>
        <div style={{ display: "flex", gap: "0.5rem", maxWidth: 460 }}>
          <input
            type="password"
            placeholder="paste token"
            value={tokenValue}
            onChange={(e) => setTokenValue(e.target.value)}
            style={{ flex: 1, padding: "0.5rem" }}
          />
          <button onClick={saveToken}>Save</button>
          <button onClick={removeToken}>Clear</button>
        </div>
      </section>
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
        <div style={{ marginTop: "1rem" }}>
          <button onClick={fetchDocs}>Fetch Docs</button>
        </div>
        {docsData && (
          <pre style={{ marginTop: "1rem", overflowX: "auto" }}>
            {docsData}
          </pre>
        )}
        {docsError && (
          <p style={{ color: "#f87171" }}>
            <strong>Docs error:</strong> {docsError}
          </p>
        )}
      </section>
    </main>
  );
}
