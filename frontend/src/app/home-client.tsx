"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { apiFetch } from "../lib/apiClient";
import { DEFAULT_API_BASE, normalizeApiBase } from "../lib/workspace";
import CitationPreviewModal from "../components/CitationPreviewModal";

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
  chunk_id?: string | null;
};

type ChatSource = {
  source_id?: string | null;
  filename?: string | null;
  page?: number | null;
  document_id?: string | null;
  chunk_id?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  text?: string | null;
};

type AnswerUnitEvidenceRef = {
  source_id?: string | null;
  page?: number | null;
  line_start?: number | null;
  line_end?: number | null;
  filename?: string | null;
  document_id?: string | null;
  chunk_id?: string | null;
};

type AnswerUnit = {
  text: string;
  citations?: AnswerUnitEvidenceRef[] | null;
};

type Answerability = {
  answerable: boolean;
  reason_code?: string | null;
  reason_message?: string | null;
  suggested_followups?: string[];
};

type ChatResponse = {
  answer?: string;
  citations?: ChatCitation[];
  sources?: ChatSource[];
  request_id?: string;
  answerability?: Answerability | null;
  answer_units?: AnswerUnit[] | null;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  citations?: ChatCitation[];
  sources?: ChatSource[];
  requestId?: string;
  answerability?: Answerability | null;
  answerUnits?: AnswerUnit[] | null;
};

const STORAGE_GLOSSARY = "ragqa.ui.glossary";
const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

const SAMPLE_PROMPTS = [
  "Summarize the obligations in section 3 of the latest policy.",
  "List key risks called out for vendor onboarding.",
  "Where is the support contact documented?",
  "What changed between the 2023 and 2024 handbook versions?",
];

type RunRecord = Record<string, unknown>;
type PreviewTarget = {
  documentId: string;
  page: number | null;
};

function resolveRunId(entry: RunRecord | null | undefined): string | null {
  if (!entry || typeof entry !== "object") return null;
  const candidates = ["run_id", "id", "request_id", "requestId"];
  for (const key of candidates) {
    const value = entry[key];
    if (typeof value === "string" && value) {
      return value;
    }
    if (typeof value === "number") {
      return String(value);
    }
  }
  return null;
}

function useGlossary() {
  const [glossary, setGlossary] = useState("");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(STORAGE_GLOSSARY);
    if (saved) setGlossary(saved);
  }, []);
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_GLOSSARY, glossary);
  }, [glossary]);
  return { glossary, setGlossary };
}

function useApi(baseUrl: string, devSub: string) {
  const normalized = normalizeApiBase(baseUrl);
  return useMemo(() => {
    async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
    async function requestRaw(path: string, init: RequestInit = {}) {
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

function citationKey(c: ChatCitation): string {
  return (
    c.source_id ||
    c.chunk_id ||
    (c.document_id ? `${c.document_id}-${c.page ?? ""}` : JSON.stringify(c))
  );
}

export default function HomeClient() {
  const baseUrl = DEFAULT_API_BASE;
  const devSub = "";
  const apiBaseLabel = normalizeApiBase(baseUrl);
  const api = useApi(baseUrl, devSub);
  const { glossary, setGlossary } = useGlossary();

  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState<string | null>(null);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [fileToUpload, setFileToUpload] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [askError, setAskError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedCitationKey, setSelectedCitationKey] = useState<string | null>(
    null,
  );
  const [runsPayload, setRunsPayload] = useState<unknown>(null);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [selectedRunEntry, setSelectedRunEntry] = useState<RunRecord | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetails, setRunDetails] = useState<unknown>(null);
  const [runDetailsError, setRunDetailsError] = useState<string | null>(null);
  const [runDetailsLoading, setRunDetailsLoading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null);
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);
  const [previewTitle, setPreviewTitle] = useState<string | null>(null);

  const refreshDocuments = useCallback(async () => {
    setDocsLoading(true);
    setDocsError(null);
    try {
      const payload = await api.request<DocumentListItem[]>("/docs");
      setDocuments(payload);
    } catch (err) {
      setDocsError((err as Error).message);
    } finally {
      setDocsLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  const refreshRuns = useCallback(async () => {
    setRunsLoading(true);
    setRunsError(null);
    try {
      const payload = await api.request<unknown>("/runs");
      setRunsPayload(payload);
    } catch (err) {
      setRunsError((err as Error).message);
    } finally {
      setRunsLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const loadRunDetails = useCallback(
    async (runId: string) => {
      setRunDetailsLoading(true);
      setRunDetailsError(null);
      try {
        const payload = await api.request<unknown>(
          `/runs/${encodeURIComponent(runId)}`,
        );
        setRunDetails(payload);
      } catch (err) {
        setRunDetailsError((err as Error).message);
        setRunDetails(null);
      } finally {
        setRunDetailsLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    setSelectedDocs((prev) =>
      prev.filter((id) => documents.some((doc) => doc.document_id === id)),
    );
  }, [documents]);

  const latestAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant") return messages[i];
    }
    return null;
  }, [messages]);

  const citations = useMemo(
    () => latestAssistant?.citations ?? [],
    [latestAssistant],
  );
  const sources = useMemo(
    () => latestAssistant?.sources ?? [],
    [latestAssistant],
  );
  const answerability = latestAssistant?.answerability ?? null;
  const answerUnits = latestAssistant?.answerUnits ?? [];

  useEffect(() => {
    if (!citations.length) {
      setSelectedCitationKey(null);
      return;
    }
    if (!selectedCitationKey) {
      setSelectedCitationKey(citationKey(citations[0]));
      return;
    }
    const stillExists = citations.some(
      (c) => citationKey(c) === selectedCitationKey,
    );
    if (!stillExists) {
      setSelectedCitationKey(citationKey(citations[0]));
    }
  }, [citations, selectedCitationKey]);

  function toggleDocSelection(docId: string) {
    setSelectedDocs((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId],
    );
  }

  function handleRunSelect(entry: RunRecord) {
    setSelectedRunEntry(entry);
    const runId = resolveRunId(entry);
    setSelectedRunId(runId);
    setRunDetails(null);
    setRunDetailsError(null);
    if (!runId) {
      setRunDetailsLoading(false);
      return;
    }
    void loadRunDetails(runId);
  }

  async function handleUpload() {
    if (!fileToUpload) {
      setUploadStatus("Select a PDF to upload.");
      return;
    }
    if (fileToUpload.size > MAX_UPLOAD_BYTES) {
      setUploadStatus("PDF must be 4 MB or smaller.");
      return;
    }
    setUploadStatus("Uploading...");
    try {
      const form = new FormData();
      form.append("file", fileToUpload);
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
    if (!window.confirm("Delete this document?")) return;
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

  function makeMessageId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  async function handleAsk() {
    const trimmed = question.trim();
    if (!trimmed) {
      setAskError("Please enter a question.");
      return;
    }
    setAskError(null);
    setSending(true);
    const newMessages: ChatMessage[] = [
      ...messages,
      {
        id: makeMessageId(),
        role: "user",
        content: trimmed,
        createdAt: Date.now(),
      },
    ];
    setMessages(newMessages);

    const payload: Record<string, unknown> = {
      question: trimmed,
      mode: selectedDocs.length ? "selected_docs" : "library",
    };
    if (selectedDocs.length) {
      payload.document_ids = selectedDocs;
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
          detail = `${detail} — verify server credentials or x-dev-sub.`;
        }
        throw new Error(detail);
      }
      const payloadJson: ChatResponse = bodyText ? JSON.parse(bodyText) : {};
      const assistantMessage: ChatMessage = {
        id: makeMessageId(),
        role: "assistant",
        content: payloadJson.answer || "(No answer returned)",
        citations: payloadJson.citations || [],
        sources: payloadJson.sources || [],
        requestId: payloadJson.request_id,
        answerability: payloadJson.answerability || null,
        answerUnits: payloadJson.answer_units || null,
        createdAt: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setQuestion("");
      const firstCitation = assistantMessage.citations?.[0];
      if (firstCitation) {
        setSelectedCitationKey(citationKey(firstCitation));
      }
    } catch (err) {
      setAskError((err as Error).message);
      setMessages((prev) => prev.filter((_, idx) => idx !== prev.length - 1));
    } finally {
      setSending(false);
    }
  }

  const selectedCitation = citations.find(
    (c) => citationKey(c) === selectedCitationKey,
  );

  const matchingSource = selectedCitation
    ? sources.find((s) => {
        if (selectedCitation.source_id && s.source_id) {
          return s.source_id === selectedCitation.source_id;
        }
        if (selectedCitation.chunk_id && s.chunk_id) {
          return s.chunk_id === selectedCitation.chunk_id;
        }
        if (selectedCitation.document_id && s.document_id) {
          return (
            s.document_id === selectedCitation.document_id &&
            (selectedCitation.page == null || s.page === selectedCitation.page)
          );
        }
        return false;
      })
    : sources[0];

  const snippetText = matchingSource?.text || selectedCitation?.filename || "";
  const injectionWarning = snippetText
    ? /pwned|ignore all instructions|system override/i.test(snippetText)
    : false;

  const runsList = Array.isArray(runsPayload)
    ? (runsPayload as RunRecord[])
    : null;
  const rawRunsPayload = runsList ? null : runsPayload;

  async function handleCopyMarkdown() {
    if (!latestAssistant) return;
    const citeLines = (latestAssistant.citations || []).map((c) => {
      const label = c.source_id ? `[${c.source_id}${c.page ? ` p.${c.page}` : ""}]` : "-";
      const file = c.filename || "Document";
      return `- ${label} ${file}`;
    });
    const markdown = `## Answer\n${latestAssistant.content || ""}\n\n## Evidence\n$${
      citeLines.length ? citeLines.join("\n") : "(none)"
    }`;
    try {
      await navigator.clipboard.writeText(markdown);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = markdown;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
  }

  function triggerPreview(
    docId: string | null,
    pageNumber: number | null,
    title?: string | null,
  ) {
    if (!docId) {
      setPreviewMessage("This citation does not include an evidence file.");
      setPreviewOpen(false);
      return;
    }
    setPreviewMessage(null);
    setPreviewTarget({ documentId: docId, page: pageNumber });
    setPreviewTitle(title || null);
    setPreviewOpen(true);
  }

  function handlePreviewTrigger() {
    const sourceCitation = selectedCitation ?? null;
    const docId =
      sourceCitation?.document_id || matchingSource?.document_id || null;
    const pageNumber =
      sourceCitation?.page != null
        ? sourceCitation.page
        : matchingSource?.page ?? null;
    triggerPreview(docId, pageNumber);
  }

  function formatEvidenceLabel(
    ref: AnswerUnitEvidenceRef,
    fallbackIndex: number,
  ): string {
    const sid = ref.source_id || `Evidence ${fallbackIndex + 1}`;
    const page = ref.page != null ? ` p.${ref.page}` : "";
    let lines = "";
    const start = ref.line_start;
    const end = ref.line_end;
    if (
      typeof start === "number" &&
      typeof end === "number" &&
      start > 0 &&
      end > 0
    ) {
      lines = ` L${start}–${end}`;
    }
    return `${sid}${page}${lines}`;
  }

  function formatAnnotationChip(
    ref: AnswerUnitEvidenceRef | null | undefined,
  ): string | null {
    if (!ref) return null;
    const page = ref.page;
    if (typeof page !== "number" || page <= 0) return null;
    const start = ref.line_start;
    const end = ref.line_end;
    if (
      typeof start === "number" &&
      typeof end === "number" &&
      start > 0 &&
      end >= start
    ) {
      return `p${page} L${start}–${end}`;
    }
    return `p${page}`;
  }

  function handleAnswerUnitPreview(ref: AnswerUnitEvidenceRef, label?: string) {
    const docId = ref.document_id || null;
    const page = ref.page ?? null;
    triggerPreview(docId, page, label || ref.source_id || "Evidence preview");
  }

  function renderAssistantContent(msg: ChatMessage): ReactNode {
    const units = msg.answerUnits || [];
    if (units.length === 0) {
      return msg.content;
    }
    return (
      <ul
        style={{
          listStyle: "disc",
          paddingLeft: "1.25rem",
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "0.45rem",
        }}
      >
        {units.map((unit, idx) => {
          const primaryRef = unit.citations?.[0] || null;
          const chipLabel = formatAnnotationChip(primaryRef);
          return (
            <li key={`${msg.id}-unit-${idx}`}>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.3rem",
                }}
              >
                <span style={{ color: "#e2e8f0" }}>{unit.text}</span>
                {chipLabel && primaryRef && (
                  <button
                    type="button"
                    onClick={() =>
                      handleAnswerUnitPreview(primaryRef, unit.text)
                    }
                    style={{
                      borderRadius: "999px",
                      border: "1px solid #334155",
                      background: "rgba(56,189,248,0.15)",
                      color: "#38bdf8",
                      fontSize: "0.75rem",
                      padding: "0.1rem 0.5rem",
                      alignSelf: "flex-start",
                      cursor: "pointer",
                    }}
                  >
                    {chipLabel}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    );
  }

  function renderSnippet(text?: string | null): ReactNode {
    if (!text) return "Snippet unavailable";
    const tokens = text.split(/(\[\[POTENTIAL_INJECTION_REDACTED_LINE\]\])/g);
    return tokens.map((part, idx) =>
      part === "[[POTENTIAL_INJECTION_REDACTED_LINE]]" ? (
        <mark key={idx}>{part}</mark>
      ) : (
        <span key={idx}>{part}</span>
      ),
    );
  }

  const containerStyle: CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    gap: "1rem",
  };

  const paneStyle: CSSProperties = {
    flex: "1 1 320px",
    minWidth: "280px",
    background: "rgba(15,23,42,0.85)",
    border: "1px solid #1e293b",
    borderRadius: "12px",
    padding: "1rem",
    color: "#e2e8f0",
  };

  return (
    <>
      <main
      style={{
        minHeight: "100vh",
        background: "radial-gradient(circle at top,#0f172a,#020617)",
        color: "#e2e8f0",
        padding: "1.5rem",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ marginBottom: "0.5rem", fontSize: "1.5rem" }}>Document Q&A</h1>
      <p style={{ marginBottom: "1rem", color: "#94a3b8", fontSize: "0.75rem" }}>
        API: {apiBaseLabel} • Auth: server managed
      </p>
      <div style={containerStyle}>
        <section style={paneStyle}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>
            Workspace
          </h2>

          <div
            style={{
              marginTop: "1.25rem",
              paddingTop: "1rem",
              borderTop: "1px solid #1e293b",
            }}
          >
            <h3 style={{ marginBottom: "0.5rem", fontSize: "1rem" }}>Documents</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setFileToUpload(e.target.files?.[0] || null)}
              />
              <button
                onClick={handleUpload}
                style={{
                  padding: "0.4rem 0.6rem",
                  borderRadius: "6px",
                  border: "1px solid #475569",
                  background: "#0ea5e9",
                  color: "#0f172a",
                  fontWeight: 600,
                }}
              >
                Upload PDF
              </button>
              {uploadStatus && (
                <p style={{ fontSize: "0.85rem", color: "#fbbf24" }}>{uploadStatus}</p>
              )}
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  onClick={() => refreshDocuments()}
                  style={{
                    padding: "0.35rem 0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #475569",
                    background: "transparent",
                    color: "#e2e8f0",
                  }}
                >
                  {docsLoading ? "Refreshing..." : "Refresh"}
                </button>
                <button
                  onClick={() => setSelectedDocs([])}
                  disabled={!selectedDocs.length}
                  style={{
                    padding: "0.35rem 0.6rem",
                    borderRadius: "6px",
                    border: "1px solid #475569",
                    background: selectedDocs.length ? "transparent" : "#1e293b",
                    color: selectedDocs.length ? "#e2e8f0" : "#475569",
                  }}
                >
                  Clear selection
                </button>
              </div>
              {docsError && (
                <p style={{ color: "#f87171", fontSize: "0.85rem" }}>{docsError}</p>
              )}
              <div
                style={{
                  maxHeight: "280px",
                  overflowY: "auto",
                  border: "1px solid #1e293b",
                  borderRadius: "8px",
                  padding: "0.5rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.4rem",
                }}
              >
                {documents.length === 0 && !docsLoading ? (
                  <p style={{ fontSize: "0.85rem", color: "#94a3b8" }}>
                    No documents yet. Upload a PDF to get started.
                  </p>
                ) : (
                  documents.map((doc) => {
                    const checked = selectedDocs.includes(doc.document_id);
                    return (
                      <div
                        key={doc.document_id}
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.2rem",
                          padding: "0.35rem",
                          borderRadius: "6px",
                          background: checked ? "rgba(14,165,233,0.1)" : "transparent",
                        }}
                      >
                        <label
                          style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleDocSelection(doc.document_id)}
                          />
                          <span>{doc.filename}</span>
                        </label>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: "0.8rem",
                            color: "#94a3b8",
                          }}
                        >
                          <span>Status: {(doc.status || "").toUpperCase()}</span>
                          <button
                            onClick={() => handleDelete(doc.document_id)}
                            style={{
                              border: "none",
                              background: "transparent",
                              color: "#f87171",
                              cursor: "pointer",
                            }}
                          >
                            Delete
                          </button>
                        </div>
                        {doc.error && (
                          <p style={{ color: "#f87171", fontSize: "0.75rem" }}>{doc.error}</p>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: "1.25rem",
              paddingTop: "1rem",
              borderTop: "1px solid #1e293b",
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            <h3 style={{ margin: 0, fontSize: "1rem" }}>Glossary</h3>
            <p style={{ fontSize: "0.8rem", color: "#94a3b8" }}>
              Optional reference notes. Stored locally on this browser.
            </p>
            <textarea
              value={glossary}
              onChange={(e) => setGlossary(e.target.value)}
              rows={6}
              placeholder="term = definition"
              style={{
                width: "100%",
                borderRadius: "8px",
                padding: "0.6rem",
                background: "#0f172a",
                color: "#e2e8f0",
              }}
            />
          </div>
        </section>

        <section style={{ ...paneStyle, flex: "2 1 480px" }}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>Ask</h2>
          <div
            style={{
              minHeight: "320px",
              border: "1px solid #1e293b",
              borderRadius: "10px",
              padding: "0.75rem",
              marginBottom: "0.75rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            {messages.length === 0 ? (
              <p style={{ color: "#94a3b8" }}>
                Ask a question about your uploaded PDFs. Citations will appear once a
                document is indexed.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {messages.map((msg) => (
                  <div key={msg.id}>
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.85rem",
                        color: msg.role === "user" ? "#38bdf8" : "#a5b4fc",
                      }}
                    >
                      {msg.role === "user" ? "You" : "Answer"}
                    </p>
                    <div
                      style={{
                        background: msg.role === "user" ? "rgba(56,189,248,0.1)" : "rgba(165,180,252,0.1)",
                        padding: "0.5rem 0.65rem",
                        borderRadius: "8px",
                        marginTop: "0.25rem",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {msg.role === "assistant"
                        ? renderAssistantContent(msg)
                        : msg.content}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
            {SAMPLE_PROMPTS.map((text) => (
              <button
                key={text}
                onClick={() => setQuestion(text)}
                style={{
                  border: "1px solid #334155",
                  borderRadius: "20px",
                  padding: "0.25rem 0.75rem",
                  background: "transparent",
                  color: "#94a3b8",
                  fontSize: "0.8rem",
                }}
              >
                {text}
              </button>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleAsk();
            }}
            style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}
          >
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={
                selectedDocs.length
                  ? "Ask about the selected documents..."
                  : "Ask about any indexed document..."
              }
              rows={4}
              style={{
                borderRadius: "8px",
                border: "1px solid #1e293b",
                padding: "0.6rem",
                background: "#0f172a",
                color: "#e2e8f0",
                resize: "vertical",
              }}
            />
            {askError && (
              <p style={{ color: "#f87171", fontSize: "0.9rem" }}>{askError}</p>
            )}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <small style={{ color: "#94a3b8" }}>
                Mode: {selectedDocs.length ? "Selected documents" : "Library"}
              </small>
              <button
                type="submit"
                disabled={sending}
                style={{
                  borderRadius: "8px",
                  padding: "0.5rem 1rem",
                  background: sending ? "#1e293b" : "#22d3ee",
                  color: sending ? "#94a3b8" : "#0f172a",
                  border: "none",
                  fontWeight: 600,
                }}
              >
                {sending ? "Thinking..." : "Ask"}
              </button>
            </div>
          </form>
        </section>

        <section style={{ ...paneStyle, flex: "1 1 340px" }}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>Evidence</h2>
          {!latestAssistant ? (
            <p style={{ color: "#94a3b8" }}>Your citations will appear here.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {answerability && (
                <div
                  style={{
                    border: "1px solid #1e293b",
                    borderRadius: "8px",
                    padding: "0.6rem",
                    background: "rgba(15,23,42,0.6)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      marginBottom: "0.35rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        borderRadius: "999px",
                        padding: "0.1rem 0.6rem",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        background: answerability.answerable
                          ? "rgba(34,197,94,0.15)"
                          : "rgba(248,113,113,0.15)",
                        color: answerability.answerable ? "#4ade80" : "#f87171",
                      }}
                    >
                      {answerability.answerable ? "Answerable" : "Needs follow-up"}
                    </span>
                    <small style={{ color: "#94a3b8" }}>
                      {answerability.reason_message ||
                        (answerability.answerable
                          ? "Answer is supported by cited sources."
                          : "Evidence is insufficient for this question.")}
                    </small>
                  </div>
                  {!answerability.answerable &&
                    (answerability.suggested_followups || []).length > 0 && (
                      <div
                        style={{
                          display: "flex",
                          gap: "0.4rem",
                          flexWrap: "wrap",
                        }}
                      >
                        {answerability.suggested_followups!.map((item, idx) => (
                          <button
                            key={`${item}-${idx}`}
                            type="button"
                            onClick={() => setQuestion(item)}
                            style={{
                              borderRadius: "999px",
                              border: "1px solid #334155",
                              background: "transparent",
                              color: "#e2e8f0",
                              fontSize: "0.75rem",
                              padding: "0.2rem 0.65rem",
                              cursor: "pointer",
                            }}
                          >
                            {item}
                          </button>
                        ))}
                      </div>
                    )}
                </div>
              )}
              <div>
                <h3 style={{ fontSize: "1rem", marginBottom: "0.25rem" }}>Citations</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                  {citations.length === 0 ? (
                    <p style={{ color: "#94a3b8", fontSize: "0.9rem" }}>
                      Answer did not include citations.
                    </p>
                  ) : (
                    citations.map((cite) => {
                      const key = citationKey(cite);
                      return (
                        <button
                          key={key}
                          onClick={() => {
                            setSelectedCitationKey(key);
                          }}
                          style={{
                            borderRadius: "8px",
                            padding: "0.4rem 0.6rem",
                            border: "1px solid #334155",
                            background:
                              selectedCitationKey === key
                                ? "rgba(34,211,238,0.15)"
                                : "transparent",
                            color: "#e2e8f0",
                            textAlign: "left",
                          }}
                        >
                          {cite.source_id || "Source"} • {cite.filename || "doc"}
                          {cite.page ? ` p.${cite.page}` : ""}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>

              {answerUnits.length > 0 && (
                <div>
                  <h3 style={{ fontSize: "1rem", marginBottom: "0.25rem" }}>Answer units</h3>
                  <p style={{ color: "#94a3b8", fontSize: "0.8rem", marginTop: 0 }}>
                    Bullets are rendered inline in the conversation. Use the chips below to preview
                    the supporting evidence for each unit.
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {answerUnits.map((unit, idx) => (
                      <div
                        key={`${unit.text}-${idx}`}
                        style={{
                          border: "1px solid #1e293b",
                          borderRadius: "8px",
                          padding: "0.5rem 0.6rem",
                          background: "rgba(15,23,42,0.6)",
                        }}
                      >
                        <p style={{ margin: 0, color: "#cbd5f5", fontSize: "0.85rem" }}>
                          Unit {idx + 1}
                        </p>
                        <div
                          style={{
                            marginTop: "0.35rem",
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "0.35rem",
                          }}
                        >
                          {unit.citations && unit.citations.length > 0 ? (
                            unit.citations.map((ref, refIdx) => (
                              <button
                                key={`${idx}-${ref.source_id || refIdx}`}
                                type="button"
                                onClick={() =>
                                  handleAnswerUnitPreview(
                                    ref,
                                    formatEvidenceLabel(ref, refIdx),
                                  )
                                }
                                style={{
                                  borderRadius: "999px",
                                  border: "1px solid #334155",
                                  background: "transparent",
                                  color: "#38bdf8",
                                  fontSize: "0.75rem",
                                  padding: "0.15rem 0.55rem",
                                  cursor: "pointer",
                                }}
                              >
                                {formatEvidenceLabel(ref, refIdx)}
                              </button>
                            ))
                          ) : (
                            <span style={{ color: "#94a3b8", fontSize: "0.8rem" }}>
                              No supporting evidence
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h3 style={{ fontSize: "1rem", marginBottom: "0.25rem" }}>Snippet</h3>
                {injectionWarning && (
                  <p style={{ color: "#fbbf24", fontSize: "0.85rem" }}>
                    Warning: snippet contains text that looks like instructions/prompt
                    injection.
                  </p>
                )}
                <pre
                  style={{
                    background: "#0f172a",
                    padding: "0.75rem",
                    borderRadius: "8px",
                    whiteSpace: "pre-wrap",
                    maxHeight: "220px",
                    overflowY: "auto",
                  }}
                >
                  {renderSnippet(snippetText)}
                </pre>
                {matchingSource?.line_start != null && matchingSource?.line_end != null && (
                  <p style={{ color: "#94a3b8", fontSize: "0.8rem", marginTop: "0.35rem" }}>
                    Lines {matchingSource.line_start}–{matchingSource.line_end}
                  </p>
                )}
                <div style={{ marginTop: "0.6rem" }}>
                  <button
                    type="button"
                    onClick={() => handlePreviewTrigger()}
                    style={{
                      borderRadius: "8px",
                      padding: "0.45rem 0.9rem",
                      border: "1px solid #334155",
                      background: "transparent",
                      color: "#e2e8f0",
                      cursor: "pointer",
                    }}
                  >
                    Preview evidence
                  </button>
                  {previewMessage && (
                    <p style={{ color: "#fbbf24", fontSize: "0.85rem", marginTop: "0.35rem" }}>
                      {previewMessage}
                    </p>
                  )}
                </div>
              </div>

              <div style={{ borderTop: "1px solid #1e293b", paddingTop: "0.75rem" }}>
                <button
                  onClick={() => handleCopyMarkdown()}
                  disabled={!latestAssistant}
                  style={{
                    borderRadius: "8px",
                    padding: "0.45rem 0.9rem",
                    border: "1px solid #334155",
                    background: latestAssistant ? "transparent" : "#1e293b",
                    color: latestAssistant ? "#e2e8f0" : "#475569",
                  }}
                >
                  Copy answer as Markdown
                </button>
              </div>
            </div>
          )}
        </section>

        <section style={{ ...paneStyle, flex: "1 1 360px" }}>
          <h2 style={{ fontSize: "1.1rem", marginBottom: "0.75rem" }}>Runs</h2>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
            <button
              onClick={() => refreshRuns()}
              style={{
                padding: "0.35rem 0.75rem",
                borderRadius: "6px",
                border: "1px solid #475569",
                background: "transparent",
                color: "#e2e8f0",
              }}
            >
              {runsLoading ? "Refreshing..." : "Refresh runs"}
            </button>
          </div>
          {runsError && (
            <p style={{ color: "#f87171", fontSize: "0.85rem" }}>{runsError}</p>
          )}
          {runsList ? (
            <div
              style={{
                maxHeight: "220px",
                overflowY: "auto",
                display: "flex",
                flexDirection: "column",
                gap: "0.4rem",
                marginBottom: "0.75rem",
              }}
            >
              {runsList.length === 0 ? (
                <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
                  No runs available yet.
                </p>
              ) : (
                runsList.map((entry, idx) => {
                  const runId = resolveRunId(entry);
                  const label = runId || `run-${idx + 1}`;
                  const isSelected = selectedRunId
                    ? runId === selectedRunId
                    : selectedRunEntry === entry;
                  return (
                    <button
                      key={`${label}-${idx}`}
                      onClick={() => handleRunSelect(entry)}
                      style={{
                        textAlign: "left",
                        borderRadius: "8px",
                        border: "1px solid #334155",
                        padding: "0.45rem 0.6rem",
                        background: isSelected
                          ? "rgba(34,211,238,0.15)"
                          : "transparent",
                        color: "#e2e8f0",
                        cursor: "pointer",
                      }}
                    >
                      <span style={{ display: "block", fontWeight: 600 }}>{label}</span>
                      <small style={{ color: "#94a3b8" }}>
                        {entry.status ? String(entry.status) : "View details"}
                      </small>
                    </button>
                  );
                })
              )}
            </div>
          ) : runsLoading ? null : rawRunsPayload ? (
            <div
              style={{
                border: "1px solid #334155",
                borderRadius: "8px",
                padding: "0.5rem",
                marginBottom: "0.75rem",
              }}
            >
              <p style={{ color: "#94a3b8", fontSize: "0.85rem", marginBottom: "0.4rem" }}>
                Runs endpoint returned an unexpected shape:
              </p>
              <pre
                style={{
                  maxHeight: "200px",
                  overflowY: "auto",
                  background: "#0f172a",
                  padding: "0.5rem",
                  borderRadius: "6px",
                }}
              >
                {JSON.stringify(rawRunsPayload, null, 2)}
              </pre>
            </div>
          ) : (
            <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
              Runs will appear after queries execute.
            </p>
          )}

          <div
            style={{
              borderTop: "1px solid #1e293b",
              paddingTop: "0.75rem",
              marginTop: "0.25rem",
            }}
          >
            <h3 style={{ fontSize: "1rem", marginBottom: "0.35rem" }}>Details</h3>
            {!selectedRunEntry ? (
              <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
                Select a run to inspect the response payload.
              </p>
            ) : (
              <>
                <p style={{ fontSize: "0.85rem", color: "#94a3b8" }}>
                  Run ID: {selectedRunId || "Not provided"}
                </p>
                {selectedRunId ? (
                  runDetailsLoading ? (
                    <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>Loading run…</p>
                  ) : runDetailsError ? (
                    <p style={{ color: "#f87171", fontSize: "0.85rem" }}>{runDetailsError}</p>
                  ) : runDetails ? (
                    <pre
                      style={{
                        background: "#0f172a",
                        padding: "0.6rem",
                        borderRadius: "8px",
                        maxHeight: "220px",
                        overflowY: "auto",
                      }}
                    >
                      {JSON.stringify(runDetails, null, 2)}
                    </pre>
                  ) : (
                    <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
                      Run details unavailable.
                    </p>
                  )
                ) : (
                  <pre
                    style={{
                      background: "#0f172a",
                      padding: "0.6rem",
                      borderRadius: "8px",
                      maxHeight: "220px",
                      overflowY: "auto",
                    }}
                  >
                    {JSON.stringify(selectedRunEntry, null, 2)}
                  </pre>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </main>
    <CitationPreviewModal
      open={previewOpen}
      onClose={() => {
        setPreviewOpen(false);
        setPreviewTitle(null);
      }}
      target={previewTarget}
      title={previewTitle || undefined}
    />
    </>
  );
}
