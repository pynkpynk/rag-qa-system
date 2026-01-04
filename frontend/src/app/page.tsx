"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { authFetch } from "../lib/apiClient";
import { clearToken, getToken, setToken } from "../lib/authToken";

type HealthResponse = {
  status: string;
  app: string;
  app_env: string;
  auth_mode: string;
  git_sha: string;
};

type DocumentListItem = {
  document_id: string;
  filename: string;
  status: string;
  error?: string | null;
};

type DocumentUploadResponse = {
  document_id: string;
  filename: string;
  status: string;
  dedup: boolean;
};

type ChatCitation = {
  source_id?: string | null;
  page?: number | null;
  filename?: string | null;
  document_id?: string | null;
  chunk_id?: string | null;
  chunk_id_missing_reason?: string | null;
};

type ChatAskResponse = {
  answer: string;
  request_id: string;
  citations: ChatCitation[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tokenValue, setTokenValue] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const [docsData, setDocsData] = useState<string | null>(null);
  const [docsError, setDocsError] = useState<string | null>(null);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsList, setDocsList] = useState<DocumentListItem[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadResp, setUploadResp] = useState<DocumentUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [askQuestion, setAskQuestion] = useState("");
  const [askMode, setAskMode] = useState("library");
  const [askResult, setAskResult] = useState<ChatAskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [askLoading, setAskLoading] = useState(false);

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

  const fetchDocsList = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setDocsError("Set a demo token first.");
      setDocsList([]);
      setDocsData(null);
      return;
    }
    setDocsError(null);
    setDocsLoading(true);
    try {
      const resp = await authFetch("/docs");
      const body = await resp.text();
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
      }
      const list = JSON.parse(body) as DocumentListItem[];
      setDocsList(list);
      setDocsData(JSON.stringify(list, null, 2));
    } catch (err) {
      setDocsList([]);
      setDocsData(null);
      setDocsError(err instanceof Error ? err.message : String(err));
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasToken) {
      void fetchDocsList();
    } else {
      setDocsList([]);
      setDocsData(null);
      setDocsError(null);
    }
  }, [hasToken, fetchDocsList]);

  useEffect(() => {
    setSelectedDocs((prev) =>
      prev.filter((id) => docsList.some((doc) => doc.document_id === id)),
    );
  }, [docsList]);

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
    const active = tokenValue.trim().length > 0;
    setHasToken(active);
    if (active) {
      void fetchDocsList();
    }
  };

  const removeToken = () => {
    clearToken();
    setTokenValue("");
    setHasToken(false);
    setSelectedDocs([]);
  };

  const toggleDocSelection = (documentId: string) => {
    setSelectedDocs((prev) =>
      prev.includes(documentId)
        ? prev.filter((id) => id !== documentId)
        : [...prev, documentId],
    );
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setUploadFile(file);
  };

  const uploadDocument = async () => {
    setUploadError(null);
    setUploadResp(null);
    if (!getToken()) {
      setUploadError("Set a demo token before uploading.");
      return;
    }
    if (!uploadFile) {
      setUploadError("Select a PDF file first.");
      return;
    }
    const form = new FormData();
    form.append("file", uploadFile);
    try {
      const resp = await authFetch("/docs/upload", {
        method: "POST",
        body: form,
      });
      const body = await resp.text();
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
      }
      const data = JSON.parse(body) as DocumentUploadResponse;
      setUploadResp(data);
      setUploadFile(null);
      await fetchDocsList();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    }
  };

  const runAsk = async () => {
    setAskError(null);
    setAskResult(null);
    if (!getToken()) {
      setAskError("Set a demo token before asking.");
      return;
    }
    if (!askQuestion.trim()) {
      setAskError("Enter a question first.");
      return;
    }
    setAskLoading(true);
    try {
      const payload = {
        mode: askMode,
        question: askQuestion,
        document_ids: selectedDocs.length > 0 ? selectedDocs : undefined,
      };
      const resp = await authFetch("/chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.text();
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
      }
      const data = JSON.parse(body) as ChatAskResponse;
      setAskResult(data);
    } catch (err) {
      setAskError(err instanceof Error ? err.message : String(err));
    } finally {
      setAskLoading(false);
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
          <button onClick={() => void fetchDocsList()} disabled={docsLoading}>
            {docsLoading ? "Loading…" : "Fetch Docs"}
          </button>
        </div>
        {docsError && (
          <p style={{ color: "#f87171" }}>
            <strong>Docs error:</strong> {docsError}
          </p>
        )}
        {docsList.length > 0 ? (
          <ul style={{ marginTop: "1rem" }}>
            {docsList.map((doc) => (
              <li key={doc.document_id}>
                <label>
                  <input
                    type="checkbox"
                    checked={selectedDocs.includes(doc.document_id)}
                    onChange={() => toggleDocSelection(doc.document_id)}
                  />{" "}
                  {doc.filename} ({doc.status})
                </label>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ marginTop: "1rem" }}>No documents yet.</p>
        )}
        {docsData && (
          <pre style={{ marginTop: "1rem", overflowX: "auto" }}>
            {docsData}
          </pre>
        )}
      </section>
      <section>
        <h2>Upload PDF</h2>
        <input
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
          style={{ marginRight: "0.5rem" }}
        />
        <button onClick={() => void uploadDocument()}>Upload PDF</button>
        {uploadResp && (
          <p style={{ marginTop: "0.5rem" }}>
            Uploaded {uploadResp.filename} (status {uploadResp.status},{" "}
            {uploadResp.dedup ? "deduped" : "new"}) – id{" "}
            <code>{uploadResp.document_id}</code>
          </p>
        )}
        {uploadError && (
          <p style={{ color: "#f87171" }}>
            <strong>Upload error:</strong> {uploadError}
          </p>
        )}
      </section>
      <section>
        <h2>Ask</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <textarea
            rows={4}
            value={askQuestion}
            onChange={(e) => setAskQuestion(e.target.value)}
            placeholder="Ask a question about the selected docs"
            style={{ padding: "0.5rem" }}
          />
          <label>
            Mode:
            <select
              value={askMode}
              onChange={(e) => setAskMode(e.target.value)}
              style={{ marginLeft: "0.5rem" }}
            >
              <option value="library">library</option>
              <option value="summary_offline_safe">summary_offline_safe</option>
            </select>
          </label>
          <button onClick={() => void runAsk()} disabled={askLoading}>
            {askLoading ? "Asking…" : "Ask"}
          </button>
        </div>
        {askError && (
          <p style={{ color: "#f87171" }}>
            <strong>Ask error:</strong> {askError}
          </p>
        )}
        {askResult && (
          <div style={{ marginTop: "1rem" }}>
            <p>
              <strong>Request:</strong> {askResult.request_id}
            </p>
            <p>
              <strong>Answer:</strong>
            </p>
            <pre style={{ whiteSpace: "pre-wrap" }}>{askResult.answer}</pre>
            <h3>Citations</h3>
            {askResult.citations.length === 0 ? (
              <p>No citations returned.</p>
            ) : (
              <ul>
                {askResult.citations.map((c, idx) => (
                  <li key={`${c.chunk_id || c.document_id || idx}`}>
                    Source {c.source_id || idx + 1} – doc{" "}
                    {c.document_id || "n/a"}, chunk {c.chunk_id || "n/a"}, page{" "}
                    {c.page ?? "?"} {c.filename ? `(${c.filename})` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
