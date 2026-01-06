"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import TokenGate from "../../components/TokenGate";
import ErrorBanner from "../../components/ErrorBanner";
import { listDocs, type DocumentListItem } from "../../lib/docClient";
import { authFetch } from "../../lib/apiClient";
import { ErrorInfo, toErrorInfo, ApiError, apiErrorFromResponse, simpleErrorInfo } from "../../lib/errors";

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
  debug_meta?: Record<string, unknown> | null;
  retrieval_debug?: Record<string, unknown> | null;
};

export default function ChatPage() {
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [docsError, setDocsError] = useState<ErrorInfo | null>(null);
  const [docsLoading, setDocsLoading] = useState(false);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [mode, setMode] = useState<"library" | "selected_docs">("library");
  const [question, setQuestion] = useState("");
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [askResult, setAskResult] = useState<ChatAskResponse | null>(null);
  const [askError, setAskError] = useState<ErrorInfo | null>(null);
  const [askLoading, setAskLoading] = useState(false);

  const refreshDocs = useCallback(async () => {
    setDocsLoading(true);
    setDocsError(null);
    try {
      const data = await listDocs();
      setDocs(data);
    } catch (err) {
      setDocs([]);
      setDocsError(toErrorInfo(err, "Failed to load documents"));
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshDocs().catch(() => null);
  }, [refreshDocs]);

  const docOptions = useMemo(() => {
    return docs.map((doc) => ({
      id: doc.document_id,
      label: `${doc.filename} (${doc.status})`,
    }));
  }, [docs]);

  const handleDocToggle = (docId: string) => {
    setSelectedDocs((prev) => {
      if (prev.includes(docId)) {
        return prev.filter((id) => id !== docId);
      }
      return [...prev, docId];
    });
  };

  const handleAsk = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setAskError(simpleErrorInfo("Question required", "Enter a question before asking."));
      return;
    }
    if (mode === "selected_docs" && selectedDocs.length === 0) {
      setAskError(
        simpleErrorInfo("Documents required", "Select at least one document or use library mode."),
      );
      return;
    }

    const payload: Record<string, unknown> = {
      mode,
      question: trimmedQuestion,
    };
    if (mode === "selected_docs") {
      payload.document_ids = selectedDocs;
    }
    payload.debug = debugEnabled;

    setAskLoading(true);
    setAskError(null);
    try {
      const resp = await authFetch("/chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const bodyText = await resp.text();
      if (!resp.ok) {
        throw apiErrorFromResponse(resp, bodyText);
      }
      let data: ChatAskResponse;
      try {
        data = JSON.parse(bodyText) as ChatAskResponse;
      } catch (parseErr) {
        throw new ApiError(
          simpleErrorInfo(
            "Invalid JSON response",
            parseErr instanceof Error ? parseErr.message : String(parseErr),
          ),
        );
      }
      setAskResult(data);
    } catch (err) {
      setAskResult(null);
      setAskError(toErrorInfo(err, "Ask failed"));
    } finally {
      setAskLoading(false);
    }
  };

  const debugPayload = useMemo(() => {
    if (!askResult) {
      return null;
    }
    return {
      debug_meta: askResult.debug_meta ?? {},
      retrieval_debug: askResult.retrieval_debug ?? {},
    };
  }, [askResult]);

  return (
    <main style={{ padding: "1rem" }}>
      <h1>Chat</h1>
      <TokenGate>
        <section
          style={{
            border: "1px solid #ddd",
            padding: "1rem",
            borderRadius: "4px",
            marginBottom: "1rem",
          }}
        >
          <h2>Ask a Question</h2>
          <form onSubmit={handleAsk}>
            <label style={{ display: "block", margin: "0.5rem 0" }}>
              Mode:
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as "library" | "selected_docs")}
                style={{ marginLeft: "0.5rem" }}
              >
                <option value="library">library</option>
                <option value="selected_docs">selected_docs</option>
              </select>
            </label>

            {mode === "selected_docs" && (
              <div
                style={{
                  border: "1px solid #e0e0e0",
                  padding: "0.5rem",
                  maxHeight: "200px",
                  overflowY: "auto",
                  marginBottom: "0.5rem",
                }}
              >
                <strong>Select documents</strong>
                {docsLoading && <p>Loading documents...</p>}
                {!docsLoading && docOptions.length === 0 && (
                  <p style={{ color: "#666" }}>No documents available.</p>
                )}
                {!docsLoading &&
                  docOptions.map((doc) => (
                    <label key={doc.id} style={{ display: "block" }}>
                      <input
                        type="checkbox"
                        checked={selectedDocs.includes(doc.id)}
                        onChange={() => handleDocToggle(doc.id)}
                      />{" "}
                      {doc.label}
                    </label>
                  ))}
                <button
                  type="button"
                  onClick={() => refreshDocs()}
                  style={{ marginTop: "0.5rem" }}
                  disabled={docsLoading}
                >
                  {docsLoading ? "Refreshing..." : "Refresh Docs"}
                </button>
                <ErrorBanner error={docsError} />
              </div>
            )}

            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={5}
              style={{ width: "100%", padding: "0.5rem", marginBottom: "0.5rem" }}
              placeholder="Ask your question..."
            />
            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <input
                type="checkbox"
                checked={debugEnabled}
                onChange={(e) => {
                  setDebugEnabled(e.target.checked);
                }}
              />
              Include debug payloads
            </label>
            <div style={{ marginTop: "0.75rem" }}>
              <button type="submit" disabled={askLoading}>
                {askLoading ? "Asking..." : "Ask"}
              </button>
            </div>
          </form>
          <ErrorBanner error={askError} />
        </section>

        {askResult && (
          <section
            style={{
              border: "1px solid #ddd",
              padding: "1rem",
              borderRadius: "4px",
            }}
          >
            <h2>Answer</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{askResult.answer}</p>
            <h3>Citations</h3>
            {askResult.citations.length === 0 && (
              <p style={{ color: "#666" }}>No citations returned.</p>
            )}
            {askResult.citations.length > 0 && (
              <ul>
                {askResult.citations.map((cite, idx) => (
                  <li
                    key={`${cite.chunk_id || cite.document_id || cite.source_id || idx}-${idx}`}
                  >
                    <div>
                      <strong>
                        {cite.filename ||
                          cite.document_id ||
                          cite.source_id ||
                          `Citation ${idx + 1}`}
                      </strong>{" "}
                      {cite.page != null && <span>p.{cite.page}</span>}
                    </div>
                    {cite.chunk_id ? (
                      <div>
                        chunk_id: <code>{cite.chunk_id}</code>
                      </div>
                    ) : (
                      <div>
                        Chunk unavailable
                        {cite.chunk_id_missing_reason
                          ? `: ${cite.chunk_id_missing_reason}`
                          : ""}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {debugEnabled && debugPayload && (
              <details style={{ marginTop: "1rem" }}>
                <summary>Debug payloads</summary>
                <div
                  style={{
                    marginTop: "0.5rem",
                    display: "grid",
                    gap: "0.5rem",
                  }}
                >
                  <div>
                    <strong>debug_meta</strong>
                    <pre
                      style={{
                        background: "#f6f8fa",
                        border: "1px solid #ddd",
                        padding: "0.75rem",
                        overflowX: "auto",
                      }}
                    >
                      {JSON.stringify(debugPayload.debug_meta, null, 2)}
                    </pre>
                  </div>
                  <div>
                    <strong>retrieval_debug</strong>
                    <pre
                      style={{
                        background: "#f6f8fa",
                        border: "1px solid #ddd",
                        padding: "0.75rem",
                        overflowX: "auto",
                      }}
                    >
                      {JSON.stringify(debugPayload.retrieval_debug, null, 2)}
                    </pre>
                  </div>
                </div>
              </details>
            )}
          </section>
        )}
      </TokenGate>
    </main>
  );
}
