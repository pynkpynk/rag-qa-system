"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../lib/apiClient";
import { DEFAULT_API_BASE, normalizeApiBase } from "../../lib/workspace";

type DocumentListItem = {
  document_id: string;
  filename: string;
  status: string;
  error?: string | null;
};

type ChatCitation = {
  source_id?: string | null;
  filename?: string | null;
  page?: number | null;
  document_id?: string | null;
};

type ChatResponse = {
  answer?: string;
  citations?: ChatCitation[];
  request_id?: string;
};

type HealthPayload = Record<string, unknown>;

type TabKey = "ask" | "documents" | "health";

const STORAGE_DEV_SUB = "ragqa.ui.devSub";

function useDevSub() {
  const [devSub, setDevSub] = useState("dev|user");

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const saved = window.localStorage.getItem(STORAGE_DEV_SUB);
    if (saved) {
      setDevSub(saved);
    }
  }, []);

  const update = useCallback((value: string) => {
    setDevSub(value);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_DEV_SUB, value);
    }
  }, []);

  return { devSub, setDevSub: update };
}

function useApi(baseUrl: string, devSub: string) {
  const normalized = normalizeApiBase(baseUrl);
  return useMemo(() => {
    async function request<T>(
      path: string,
      init: RequestInit = {},
    ): Promise<T> {
      const resp = await apiFetch(
        normalized,
        path,
        devSub || undefined,
        init,
      );
      const text = await resp.text();
      const payload = text ? JSON.parse(text) : null;
      if (!resp.ok) {
        const errMessage =
          (payload && payload.error && payload.error.message) ||
          payload?.message ||
          resp.statusText;
        throw new Error(errMessage || "Request failed");
      }
      return payload as T;
    }
    async function requestRaw(
      path: string,
      init: RequestInit = {},
    ): Promise<Response> {
      return apiFetch(
        normalized,
        path,
        devSub || undefined,
        init,
      );
    }
    return { request, requestRaw };
  }, [normalized, devSub]);
}

export default function DevClient() {
  const { devSub, setDevSub } = useDevSub();
  const baseUrl = DEFAULT_API_BASE;
  const api = useApi(baseUrl, devSub);
  const [activeTab, setActiveTab] = useState<TabKey>("ask");

  const [healthData, setHealthData] = useState<HealthPayload | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState<string | null>(null);
  const [fileToUpload, setFileToUpload] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [askMode, setAskMode] = useState("library");
  const [docIdsInput, setDocIdsInput] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [askResult, setAskResult] = useState<ChatResponse | null>(null);

  const refreshDocuments = useCallback(async () => {
    setDocsLoading(true);
    setDocsError(null);
    try {
      const payload = await api.request<DocumentListItem[]>("/docs");
      setDocs(payload);
    } catch (err) {
      setDocsError((err as Error).message);
    } finally {
      setDocsLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (activeTab === "documents") {
      void refreshDocuments();
    }
  }, [activeTab, refreshDocuments]);

  async function handleUpload() {
    if (!fileToUpload) {
      setUploadStatus("Select a PDF to upload.");
      return;
    }
    setUploadStatus("Uploading...");
    const form = new FormData();
    form.append("file", fileToUpload);
    try {
      const resp = await api.requestRaw("/docs/upload", {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || resp.statusText);
      }
      setUploadStatus("Upload complete.");
      setFileToUpload(null);
      await refreshDocuments();
    } catch (err) {
      setUploadStatus((err as Error).message);
    }
  }

  async function handleDelete(docId: string) {
    if (!window.confirm("Delete this document?")) {
      return;
    }
    try {
      const resp = await api.requestRaw(`/docs/${docId}`, { method: "DELETE" });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || resp.statusText);
      }
      await refreshDocuments();
    } catch (err) {
      setDocsError((err as Error).message);
    }
  }

  async function handleHealthCheck() {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const payload = await api.request<HealthPayload>("/health");
      setHealthData(payload);
    } catch (err) {
      setHealthError((err as Error).message);
      setHealthData(null);
    } finally {
      setHealthLoading(false);
    }
  }

  async function handleAsk() {
    setAskLoading(true);
    setAskError(null);
    setAskResult(null);
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setAskLoading(false);
      setAskError("Please enter a question.");
      return;
    }
    const payload: Record<string, unknown> = {
      question: trimmedQuestion,
      mode: askMode,
    };
    if (askMode === "selected_docs") {
      const cleaned = docIdsInput
        .split(/[\n,]/)
        .map((id) => id.trim())
        .filter(Boolean);
      payload.document_ids = cleaned;
    }
    try {
      const resp = await api.requestRaw("/chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const bodyText = await resp.text();
      if (!resp.ok) {
        let detail = resp.statusText || "Request failed";
        try {
          const parsed = bodyText ? JSON.parse(bodyText) : null;
          if (parsed && parsed.error) {
            const code = parsed.error.code ? `[${parsed.error.code}] ` : "";
            detail = `${code}${parsed.error.message || detail}`;
          } else if (parsed?.message) {
            detail = parsed.message;
          }
        } catch {
          /* ignore */
        }
        if (resp.status === 401) {
          detail = `${detail} — verify server credentials and x-dev-sub.`;
        }
        throw new Error(detail);
      }
      const payloadJson: ChatResponse = bodyText ? JSON.parse(bodyText) : {};
      setAskResult(payloadJson);
    } catch (err) {
      const message = (err as Error).message;
      setAskError(message);
    } finally {
      setAskLoading(false);
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0f172a",
        color: "#e2e8f0",
        fontFamily: "system-ui, sans-serif",
        padding: "1.5rem",
      }}
    >
      <section
        style={{
          border: "1px solid #334155",
          borderRadius: "6px",
          padding: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <h1 style={{ marginBottom: "0.5rem" }}>RAG QA Console (MVP)</h1>
        <p style={{ marginBottom: "0.75rem", color: "#94a3b8" }}>
          Requests proxy through <code>/api</code> with server-managed credentials.
          Adjust the dev subject if you need to impersonate a specific tenant user.
        </p>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          Dev subject (x-dev-sub)
          <input
            value={devSub}
            onChange={(e) => setDevSub(e.target.value)}
            placeholder="dev|user"
            style={{ padding: "0.4rem", borderRadius: "4px" }}
          />
        </label>
      </section>

      <section>
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          {(["ask", "documents", "health"] as TabKey[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "4px",
                border: "1px solid #475569",
                background: activeTab === tab ? "#1d4ed8" : "transparent",
                color: "#e2e8f0",
                cursor: "pointer",
              }}
            >
              {tab === "ask"
                ? "Ask"
                : tab === "documents"
                ? "Documents"
                : "Health"}
            </button>
          ))}
        </div>

        {activeTab === "health" && (
          <div
            style={{
              border: "1px solid #334155",
              borderRadius: "6px",
              padding: "1rem",
            }}
          >
            <button
              onClick={handleHealthCheck}
              disabled={healthLoading}
              style={{
                padding: "0.4rem 0.8rem",
                borderRadius: "4px",
                background: "#1d4ed8",
                color: "#fff",
                border: "none",
                cursor: "pointer",
              }}
            >
              {healthLoading ? "Checking..." : "Check health"}
            </button>
            {healthError && (
              <p style={{ marginTop: "0.75rem", color: "#f87171" }}>{healthError}</p>
            )}
            {healthData && (
              <pre
                style={{
                  marginTop: "0.75rem",
                  padding: "0.75rem",
                  background: "#020617",
                  borderRadius: "4px",
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(healthData, null, 2)}
              </pre>
            )}
          </div>
        )}

        {activeTab === "documents" && (
          <div
            style={{
              border: "1px solid #334155",
              borderRadius: "6px",
              padding: "1rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <button
                onClick={refreshDocuments}
                disabled={docsLoading}
                style={{
                  padding: "0.4rem 0.8rem",
                  borderRadius: "4px",
                  background: "#1d4ed8",
                  color: "#fff",
                  border: "none",
                }}
              >
                {docsLoading ? "Loading..." : "Refresh"}
              </button>
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setFileToUpload(e.target.files?.[0] || null)}
              />
              <button
                onClick={handleUpload}
                disabled={!fileToUpload}
                style={{
                  padding: "0.4rem 0.8rem",
                  borderRadius: "4px",
                  background: fileToUpload ? "#0f766e" : "#475569",
                  color: "#fff",
                  border: "none",
                }}
              >
                Upload PDF
              </button>
            </div>
            {uploadStatus && <p>{uploadStatus}</p>}
            {docsError && <p style={{ color: "#f87171" }}>{docsError}</p>}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {docs.map((doc) => (
                <div
                  key={doc.document_id}
                  style={{
                    border: "1px solid #334155",
                    borderRadius: "4px",
                    padding: "0.5rem",
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.75rem",
                  }}
                >
                  <div>
                    <strong>{doc.filename}</strong>
                    <div style={{ fontSize: "0.85rem", color: "#94a3b8" }}>
                      <div>ID: {doc.document_id}</div>
                      <div>Status: {doc.status}</div>
                      {doc.error && <div>Error: {doc.error}</div>}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.document_id)}
                    style={{
                      padding: "0.25rem 0.6rem",
                      background: "#b91c1c",
                      color: "#fff",
                      border: "none",
                      borderRadius: "4px",
                    }}
                  >
                    Delete
                  </button>
                </div>
              ))}
              {docs.length === 0 && !docsLoading && (
                <p>No documents found. Upload a PDF to get started.</p>
              )}
            </div>
          </div>
        )}

        {activeTab === "ask" && (
          <div
            style={{
              border: "1px solid #334155",
              borderRadius: "6px",
              padding: "1rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question..."
              rows={4}
              style={{ padding: "0.5rem", borderRadius: "4px" }}
            />
            <label>
              Mode:
              <select
                value={askMode}
                onChange={(e) => setAskMode(e.target.value)}
                style={{ marginLeft: "0.5rem" }}
              >
                <option value="library">library</option>
                <option value="selected_docs">selected_docs</option>
              </select>
            </label>
            {askMode === "selected_docs" && (
              <textarea
                value={docIdsInput}
                onChange={(e) => setDocIdsInput(e.target.value)}
                placeholder="Document IDs (comma or newline separated)"
                rows={3}
                style={{ padding: "0.5rem", borderRadius: "4px" }}
              />
            )}
            <button
              onClick={handleAsk}
              disabled={askLoading || !question.trim()}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "4px",
                border: "none",
                background: "#1d4ed8",
                color: "#fff",
              }}
            >
              {askLoading ? "Asking..." : "Ask"}
            </button>
            {askError && <p style={{ color: "#f87171" }}>{askError}</p>}
            {askResult && (
              <div
                style={{
                  border: "1px solid #1e293b",
                  padding: "0.75rem",
                  borderRadius: "4px",
                }}
              >
                <h3>Answer</h3>
                <p style={{ whiteSpace: "pre-wrap" }}>{askResult.answer}</p>
                {askResult.citations && askResult.citations.length > 0 && (
                  <div>
                    <h4>Citations</h4>
                    <ul>
                      {askResult.citations.map((cite, idx) => (
                        <li key={idx}>
                          {cite.source_id || "S"} — {cite.filename || "file"} (page{" "}
                          {cite.page ?? "?"})
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {docs.length === 0 && !docsLoading && (
              <p style={{ color: "#94a3b8" }}>
                Upload a document to get citations in Ask responses.
              </p>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
