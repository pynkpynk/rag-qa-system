"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { authFetch } from "../lib/apiClient";
import { clearToken, getToken, setToken } from "../lib/authToken";
import {
  attachDocsToRun,
  createRun,
  getRun,
  listRuns,
  type RunDetail,
  type RunListItem,
} from "../lib/runClient";
import { getChunk, type ChunkDetail } from "../lib/chunkClient";
import { deleteDoc } from "../lib/docClient";

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
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runsLoading, setRunsLoading] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [runActionMessage, setRunActionMessage] = useState<string | null>(null);
  const [runActionError, setRunActionError] = useState<string | null>(null);
  const [useRunScope, setUseRunScope] = useState(false);
  const [chunkDetails, setChunkDetails] = useState<Record<string, ChunkDetail>>({});
  const [chunkErrors, setChunkErrors] = useState<Record<string, string | null>>({});
  const [chunkLoadingState, setChunkLoadingState] = useState<Record<string, boolean>>(
    {},
  );
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const [docsActionError, setDocsActionError] = useState<string | null>(null);

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

  const fetchRunsList = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setRunsError("Set a demo token first.");
      setRuns([]);
      return;
    }
    setRunsError(null);
    setRunsLoading(true);
    try {
      const data = await listRuns();
      setRuns(data);
    } catch (err) {
      setRuns([]);
      setRunsError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunsLoading(false);
    }
  }, []);

  const loadRunDetail = useCallback(async (runId: string) => {
    setRunDetailError(null);
    setRunDetailLoading(true);
    try {
      const data = await getRun(runId);
      setRunDetail(data);
    } catch (err) {
      setRunDetail(null);
      setRunDetailError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasToken) {
      void fetchDocsList();
      void fetchRunsList();
    } else {
      setDocsList([]);
      setDocsData(null);
      setDocsError(null);
      setRuns([]);
      setRunsError(null);
      setSelectedRunId(null);
      setRunDetail(null);
      setUseRunScope(false);
    }
  }, [hasToken, fetchDocsList, fetchRunsList]);

  useEffect(() => {
    setSelectedDocs((prev) =>
      prev.filter((id) => docsList.some((doc) => doc.document_id === id)),
    );
  }, [docsList]);

  useEffect(() => {
    if (!selectedRunId) {
      setRunDetail(null);
      setRunDetailError(null);
      setRunDetailLoading(false);
      setUseRunScope(false);
      return;
    }
    setUseRunScope((prev) => (prev ? prev : true));
    void loadRunDetail(selectedRunId);
  }, [selectedRunId, loadRunDetail]);

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
      void fetchRunsList();
    }
  };

  const removeToken = () => {
    clearToken();
    setTokenValue("");
    setHasToken(false);
    setSelectedDocs([]);
    setSelectedRunId(null);
    setRuns([]);
    setRunDetail(null);
  };

  const toggleDocSelection = (documentId: string) => {
    setSelectedDocs((prev) =>
      prev.includes(documentId)
        ? prev.filter((id) => id !== documentId)
        : [...prev, documentId],
    );
  };

  const selectRun = (runId: string) => {
    if (runId === selectedRunId) {
      return;
    }
    setRunActionError(null);
    setRunActionMessage(null);
    setSelectedRunId(runId);
  };

  const handleDeleteDoc = async (documentId: string) => {
    setDocsActionError(null);
    setDeletingDocId(documentId);
    try {
      await deleteDoc(documentId);
      await fetchDocsList();
      setSelectedDocs((prev) => prev.filter((id) => id !== documentId));
    } catch (err) {
      setDocsActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeletingDocId(null);
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setUploadFile(file);
  };

  const copyText = async (text: string) => {
    if (!text) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore clipboard errors (browser may block)
    }
  };

  const fetchCitationChunk = async (chunkId: string) => {
    if (!chunkId) {
      return;
    }
    setChunkErrors((prev) => ({ ...prev, [chunkId]: null }));
    setChunkLoadingState((prev) => ({ ...prev, [chunkId]: true }));
    try {
      const detail = await getChunk(chunkId);
      setChunkDetails((prev) => ({ ...prev, [chunkId]: detail }));
    } catch (err) {
      setChunkDetails((prev) => {
        const next = { ...prev };
        delete next[chunkId];
        return next;
      });
      setChunkErrors((prev) => ({
        ...prev,
        [chunkId]: err instanceof Error ? err.message : String(err),
      }));
    } finally {
      setChunkLoadingState((prev) => ({ ...prev, [chunkId]: false }));
    }
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

  const handleCreateRun = async () => {
    setRunActionError(null);
    setRunActionMessage(null);
    if (!getToken()) {
      setRunActionError("Set a demo token before creating runs.");
      return;
    }
    try {
      const run = await createRun({ mode: askMode }, selectedDocs);
      setRunActionMessage(`Run ${run.run_id} created.`);
      await fetchRunsList();
      setSelectedRunId(run.run_id);
    } catch (err) {
      setRunActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleAttachDocs = async () => {
    setRunActionError(null);
    setRunActionMessage(null);
    if (!selectedRunId) {
      setRunActionError("Select a run before attaching documents.");
      return;
    }
    if (selectedDocs.length === 0) {
      setRunActionError("Select at least one document to attach.");
      return;
    }
    try {
      const detail = await attachDocsToRun(selectedRunId, selectedDocs);
      setRunDetail(detail);
      setRunActionMessage("Documents attached to run.");
      await fetchRunsList();
    } catch (err) {
      setRunActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const formatCitationLabel = (citation: ChatCitation, idx: number): string => {
    const base = citation.source_id || `S${idx + 1}`;
    const pagePart =
      typeof citation.page === "number" && Number.isFinite(citation.page)
        ? ` p.${citation.page}`
        : "";
    return `[${base}${pagePart}]`;
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
    if (useRunScope && !selectedRunId) {
      setAskError("Select a run or disable run scope.");
      return;
    }
    setAskLoading(true);
    try {
      const payload: Record<string, unknown> = {
        mode: askMode,
        question: askQuestion,
      };
      if (useRunScope && selectedRunId) {
        payload.run_id = selectedRunId;
      } else if (selectedDocs.length > 0) {
        payload.document_ids = selectedDocs;
      }
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
      <section>
        <h2>Runs</h2>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button onClick={() => void fetchRunsList()} disabled={runsLoading}>
            {runsLoading ? "Loading…" : "Fetch Runs"}
          </button>
          <button onClick={() => void handleCreateRun()}>Create Run</button>
          {selectedRunId && (
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
              <input
                type="checkbox"
                checked={useRunScope}
                onChange={(e) => setUseRunScope(e.target.checked)}
              />
              Ask using run scope (<code>{selectedRunId}</code>)
            </label>
          )}
        </div>
        {runsError && (
          <p style={{ color: "#f87171" }}>
            <strong>Runs error:</strong> {runsError}
          </p>
        )}
        {runActionError && (
          <p style={{ color: "#f97316" }}>
            <strong>Run action error:</strong> {runActionError}
          </p>
        )}
        {runActionMessage && (
          <p style={{ color: "#4ade80" }}>{runActionMessage}</p>
        )}
        {runs.length > 0 ? (
          <ul style={{ marginTop: "1rem" }}>
            {runs.map((run) => (
              <li key={run.run_id} style={{ marginBottom: "0.25rem" }}>
                <button onClick={() => selectRun(run.run_id)}>
                  {selectedRunId === run.run_id ? "Selected" : "Select"}
                </button>{" "}
                <code>{run.run_id}</code> – {run.status} ({run.document_ids.length} docs)
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ marginTop: "1rem" }}>No runs yet.</p>
        )}
        {selectedRunId && (
          <div style={{ marginTop: "1rem" }}>
            <p>
              <strong>Run detail:</strong>{" "}
              <code>{selectedRunId}</code>
            </p>
            {runDetailLoading && <p>Loading run…</p>}
            {runDetailError && (
              <p style={{ color: "#f87171" }}>
                <strong>Run detail error:</strong> {runDetailError}
              </p>
            )}
            {runDetail && (
              <>
                <ul>
                  <li>Status: {runDetail.status}</li>
                  <li>Error: {runDetail.error || "none"}</li>
                  <li>Documents: {runDetail.document_ids.join(", ") || "none"}</li>
                </ul>
                <button
                  onClick={() => void handleAttachDocs()}
                  disabled={selectedDocs.length === 0}
                >
                  Attach selected docs
                </button>
                <pre style={{ marginTop: "0.5rem", overflowX: "auto" }}>
                  {JSON.stringify(runDetail, null, 2)}
                </pre>
              </>
            )}
          </div>
        )}
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
        {docsActionError && (
          <p style={{ color: "#f97316" }}>
            <strong>Doc action error:</strong> {docsActionError}
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
                <button
                  style={{ marginLeft: "0.5rem" }}
                  onClick={() => void handleDeleteDoc(doc.document_id)}
                  disabled={deletingDocId === doc.document_id}
                >
                  {deletingDocId === doc.document_id ? "Deleting…" : "Delete"}
                </button>
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
                {askResult.citations.map((c, idx) => {
                  const chunkId = c.chunk_id || "";
                  const detail = chunkId ? chunkDetails[chunkId] : undefined;
                  const chunkLoading = chunkId
                    ? chunkLoadingState[chunkId]
                    : false;
                  const chunkErr = chunkId ? chunkErrors[chunkId] : null;
                  const label = formatCitationLabel(c, idx);
                  return (
                    <li key={`${chunkId || c.document_id || idx}`}>
                      <p>
                        {label}: doc {c.document_id || "n/a"}, chunk{" "}
                        {chunkId || "n/a"}, page {c.page ?? "?"}{" "}
                        {c.filename ? `(${c.filename})` : ""}
                      </p>
                      {chunkId && (
                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          <button
                            onClick={() => void fetchCitationChunk(chunkId)}
                            disabled={chunkLoading}
                          >
                            {chunkLoading
                              ? "Loading…"
                              : detail
                                ? "Refresh excerpt"
                                : "Show excerpt"}
                          </button>
                          <button onClick={() => void copyText(chunkId)}>
                            Copy chunk_id
                          </button>
                          <button onClick={() => void copyText(label)}>
                            Copy label
                          </button>
                        </div>
                      )}
                      {chunkErr && (
                        <p style={{ color: "#f87171" }}>
                          <strong>Chunk error:</strong> {chunkErr}
                        </p>
                      )}
                      {detail && chunkId === detail.chunk_id && (
                        <pre
                          style={{
                            marginTop: "0.5rem",
                            padding: "0.5rem",
                            background: "#1e293b",
                            borderRadius: "4px",
                          }}
                        >
                          {detail.text}
                        </pre>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
