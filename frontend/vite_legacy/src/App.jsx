import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import "./style.css";

const API_BASE = "/api";

function healthDotStyle(ok) {
  return {
    display: "inline-block",
    width: 10,
    height: 10,
    borderRadius: 9999,
    background: ok === null ? "#999" : ok ? "#2ecc71" : "#e74c3c",
    marginRight: 6,
    verticalAlign: "middle",
  };
}

/** PDFビューアの #page は多くの場合 1-start */
function normalizePdfPage(page) {
  const p = Number(page);
  if (!Number.isFinite(p)) return 1;
  return Math.max(1, p);
}

function pdfDownloadUrl(documentId) {
  if (!documentId) return null;
  return `${API_BASE}/docs/${encodeURIComponent(documentId)}/download`;
}

/** ✅ inline表示用（自動DL回避の本命） */
function pdfViewUrl(documentId) {
  if (!documentId) return null;
  return `${API_BASE}/docs/${encodeURIComponent(documentId)}/view`;
}

function pdfPageHash(page) {
  const p = normalizePdfPage(page);
  return `#page=${p}`;
}

function formatDocIds(ids) {
  if (!ids?.length) return "(none)";
  if (ids.length <= 2) return ids.join(", ");
  return `${ids.length} doc(s): ${ids[0]}, ${ids[1]}, ...`;
}

async function safeCopy(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    window.prompt("Copy this:", text);
    return false;
  }
}

async function waitUntilIndexed(targetDocId, { intervalMs = 1000, timeoutMs = 60000 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const docs = await api.listDocs();
    const hit = docs.find((d) => d.document_id === targetDocId);
    if (!hit) return { done: true, status: "missing" };
    if (hit.status === "indexed") return { done: true, status: "indexed" };
    if (hit.status === "failed") return { done: true, status: "failed", error: hit.error };
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return { done: false, status: "timeout" };
}

/** api.attachDocs がない場合のフォールバック（/api/runs/{run_id}/attach_docs） */
async function attachDocsFallback(runId, documentIds) {
  const res = await api.authorizedFetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/attach_docs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_ids: documentIds }),
  });

  if (!res.ok) {
    const ct = res.headers.get("content-type") || "";
    let msg = `${res.status} ${res.statusText}`;
    try {
      if (ct.includes("application/json")) {
        const j = await res.json();
        msg = j?.detail || JSON.stringify(j);
      } else {
        const t = await res.text();
        msg = t || msg;
      }
    } catch {
      // noop
    }
    throw new Error(msg);
  }

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return null;
}

/**
 * ✅ P04: citationsは document_id を返す設計だが、念のため fallback を残す
 * source_id(=filename想定) から docs[] を使って document_id を推定
 */
function resolveDocIdFromSourceId(sourceId, docs) {
  if (!sourceId) return null;

  const exact = (docs || []).find((d) => d?.filename === sourceId);
  if (exact?.document_id) return exact.document_id;

  const loose = (docs || []).find((d) => {
    const fn = d?.filename || "";
    return fn && (fn.includes(sourceId) || sourceId.includes(fn));
  });
  if (loose?.document_id) return loose.document_id;

  return null;
}

/**
 * ✅ /view を fetch→objectURL で iframe 表示
 */
async function fetchPdfAsObjectUrl(documentId, { signal } = {}) {
  const url = pdfViewUrl(documentId);
  if (!url) throw new Error("documentId is missing");

  const res = await api.authorizedFetch(url, { method: "GET", signal, cache: "no-store" });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(t || `${res.status} ${res.statusText}`);
  }
  const blob = await res.blob();
  const pdfBlob = blob.type === "application/pdf" ? blob : new Blob([blob], { type: "application/pdf" });
  return URL.createObjectURL(pdfBlob);
}

export default function App() {
  const [docs, setDocs] = useState([]);
  const [runs, setRuns] = useState([]);

  const [uploadResult, setUploadResult] = useState("");

  const [runsBusy, setRunsBusy] = useState(false);
  const [runsError, setRunsError] = useState("");

  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState("");
  const [runId, setRunId] = useState("");
  const [runDocIds, setRunDocIds] = useState([]);
  const [runConfigText, setRunConfigText] = useState("(none)");

  const [question, setQuestion] = useState(
    "What is the P1 response time target for the Pro plan? Answer with citations."
  );
  const [k, setK] = useState(6);
  const [askBusy, setAskBusy] = useState(false);
  const [askError, setAskError] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [citations, setCitations] = useState([]);

  const [drillBusy, setDrillBusy] = useState(false);
  const [drillError, setDrillError] = useState("");
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [selectedChunk, setSelectedChunk] = useState(null);
  const [pageChunks, setPageChunks] = useState([]);

  const [cleanupOlderDays, setCleanupOlderDays] = useState(1);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupError, setCleanupError] = useState("");
  const [cleanupResult, setCleanupResult] = useState("(none)");

  const [tokenDraft, setTokenDraft] = useState("");
  const [tokenStatus, setTokenStatus] = useState("");
  const [savedToken, setSavedToken] = useState("");

  // health indicator
  const [backendOk, setBackendOk] = useState(null);
  const [backendMeta, setBackendMeta] = useState(null);
  const llmEnabled = backendMeta?.llm_enabled ?? null;
  const llmStatusText = backendMeta
    ? backendMeta.llm_enabled
      ? "LLM: enabled"
      : "LLM: offline (extractive mode)"
    : "LLM: unknown";
  const llmWarning = backendMeta?.llm_enabled === false;

  // multi-doc selection
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const selectedDocSet = useMemo(() => new Set(selectedDocIds), [selectedDocIds]);

  const disableGlobal = runsBusy || runBusy || askBusy || drillBusy || cleanupBusy;
  const hasToken = Boolean((savedToken || "").trim());

  // highlight: docs attached to selected run
  const docsHighlightSet = useMemo(() => new Set(runDocIds || []), [runDocIds]);

  const indexedDocIds = useMemo(
    () => (docs || []).filter((d) => d.status === "indexed").map((d) => d.document_id),
    [docs]
  );

  const indexedSelectedCount = useMemo(() => {
    const indexed = new Set(indexedDocIds);
    return selectedDocIds.filter((id) => indexed.has(id)).length;
  }, [selectedDocIds, indexedDocIds]);

  const allIndexedSelected = useMemo(() => {
    if (!indexedDocIds.length) return false;
    return indexedDocIds.every((id) => selectedDocSet.has(id));
  }, [indexedDocIds, selectedDocSet]);

  const singleDocScopeId = !runId && selectedDocIds.length === 1 ? selectedDocIds[0] : null;
  const askDisabled = disableGlobal || !hasToken || (!runId && !singleDocScopeId);
  const scopeLabel = runId
    ? `Run ${runId}`
    : singleDocScopeId
    ? `Doc ${filenameOf(singleDocScopeId) || singleDocScopeId}`
    : "Select a run or exactly one document";

  useEffect(() => {
    const initial = api.getAuthToken() || "";
    setTokenDraft(initial);
    setSavedToken(initial);
  }, []);

  useEffect(() => {
    if (!tokenStatus) return;
    const id = setTimeout(() => setTokenStatus(""), 3000);
    return () => clearTimeout(id);
  }, [tokenStatus]);

  // PDF preview (objectURL)
  const [pdfPreviewEnabled, setPdfPreviewEnabled] = useState(false);
  const [pdfPreviewBusy, setPdfPreviewBusy] = useState(false);
  const [pdfPreviewError, setPdfPreviewError] = useState("");
  const [pdfObjectUrl, setPdfObjectUrl] = useState(null);
  const pdfAbortRef = useRef(null);

  // P04: page chunk scroll refs
  const pageChunkRefs = useRef(new Map()); // chunk_id -> HTMLElement

  const drillDocId = useMemo(() => {
    return (
      selectedCitation?.document_id ??
      selectedChunk?.document_id ??
      resolveDocIdFromSourceId(selectedCitation?.source_id, docs) ??
      null
    );
  }, [selectedCitation, selectedChunk, docs]);

  const drillPage = selectedCitation?.page ?? selectedChunk?.page ?? null;

  const drillPdfIframeSrc = useMemo(() => {
    if (!pdfObjectUrl) return null;
    return `${pdfObjectUrl}${pdfPageHash(drillPage)}`;
  }, [pdfObjectUrl, drillPage]);

  // cleanup: objectURL
  useEffect(() => {
    return () => {
      if (pdfAbortRef.current) pdfAbortRef.current.abort();
      if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // backend health polling
  useEffect(() => {
    let cancelled = false;

    const ping = async () => {
      try {
        const res = await api.authorizedFetch(`${API_BASE}/health`, { cache: "no-store" });
        if (!res.ok) {
          if (!cancelled) {
            setBackendOk(false);
            setBackendMeta(null);
          }
          return;
        }
        const j = await res.json().catch(() => null);
        if (!cancelled) {
          setBackendOk(true);
          setBackendMeta(j);
        }
      } catch {
        if (!cancelled) {
          setBackendOk(false);
          setBackendMeta(null);
        }
      }
    };

    ping();
    const id = setInterval(ping, 8000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  function clearAnswerAndDrill() {
    setAskError("");
    setAnswerText("");
    setCitations([]);
    setSelectedCitation(null);
    setSelectedChunk(null);
    setPageChunks([]);
    setDrillError("");

    setPdfPreviewEnabled(false);
    setPdfPreviewBusy(false);
    setPdfPreviewError("");
    if (pdfAbortRef.current) pdfAbortRef.current.abort();
    pdfAbortRef.current = null;
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    setPdfObjectUrl(null);

    pageChunkRefs.current = new Map();
  }

  function saveAuthToken() {
    api.setAuthToken(tokenDraft);
    const next = api.getAuthToken() || "";
    setTokenDraft(next);
    setSavedToken(next);
    setTokenStatus(next ? "Token saved." : "Token cleared.");
  }

  function clearAuthToken() {
    api.clearAuthToken();
    setTokenDraft("");
    setSavedToken("");
    setTokenStatus("Token cleared.");
  }

  function defaultRunConfig() {
    return { model: "gpt-5-mini", chunk: { size: 800, overlap: 120 }, retriever: { k: 8 } };
  }

  function indexedDocIdSetFrom(docsList) {
    return new Set((docsList || []).filter((d) => d.status === "indexed").map((d) => d.document_id));
  }

  function toggleDocSelect(docId) {
    setSelectedDocIds((prev) => {
      const s = new Set(prev);
      if (s.has(docId)) s.delete(docId);
      else s.add(docId);
      return Array.from(s);
    });
  }

  function clearDocSelection() {
    setSelectedDocIds([]);
  }

  function toggleSelectAllIndexed() {
    if (allIndexedSelected) {
      setSelectedDocIds((prev) => prev.filter((id) => !indexedDocIds.includes(id)));
    } else {
      setSelectedDocIds((prev) => Array.from(new Set([...prev, ...indexedDocIds])));
    }
  }

  useEffect(() => {
    const existing = new Set((docs || []).map((d) => d.document_id));
    setSelectedDocIds((prev) => prev.filter((id) => existing.has(id)));
  }, [docs]);

  async function refreshDocs() {
    const d = await api.listDocs();
    setDocs(d);
  }

  async function refreshRuns() {
    setRunsBusy(true);
    setRunsError("");
    try {
      const r = await api.listRuns();
      setRuns(r);
    } catch (e) {
      setRunsError(String(e?.message || e));
    } finally {
      setRunsBusy(false);
    }
  }

  async function selectRun(id) {
    setRunBusy(true);
    setRunError("");
    clearAnswerAndDrill();
    try {
      const data = await api.getRun(id);
      setRunId(data.run_id);
      setRunDocIds(Array.isArray(data.document_ids) ? data.document_ids : []);
      setRunConfigText(data.config ? JSON.stringify(data.config, null, 2) : "(none)");
    } catch (e) {
      setRunError(String(e?.message || e));
    } finally {
      setRunBusy(false);
    }
  }

  async function createRunForDoc(documentId) {
    setRunBusy(true);
    setRunError("");
    clearAnswerAndDrill();
    try {
      const payload = { config: defaultRunConfig(), document_ids: [documentId] };
      const created = await api.createRun(payload);
      await selectRun(created.run_id);
      await refreshRuns();
    } catch (e) {
      setRunError(String(e?.message || e));
    } finally {
      setRunBusy(false);
    }
  }

  async function createRunFromSelectedDocs() {
    const ids = selectedDocIds.slice();
    if (!ids.length) return;

    setRunError("");

    const indexed = indexedDocIdSetFrom(docs);
    const safeIds = ids.filter((id) => indexed.has(id));
    const notIndexed = ids.filter((id) => !indexed.has(id));

    if (!safeIds.length) {
      setRunError("Selected docs are not indexed yet.");
      return;
    }
    if (notIndexed.length) {
      setRunError(`Note: ${notIndexed.length} selected doc(s) were skipped (not indexed).`);
    }

    setRunBusy(true);
    clearAnswerAndDrill();
    try {
      const payload = { config: defaultRunConfig(), document_ids: safeIds };
      const created = await api.createRun(payload);
      await selectRun(created.run_id);
      await refreshRuns();
      await refreshDocs();
    } catch (e) {
      setRunError(String(e?.message || e));
    } finally {
      setRunBusy(false);
    }
  }

  async function attachSelectedDocsToCurrentRun() {
    if (!runId) {
      setRunError("Select a run first.");
      return;
    }
    const ids = selectedDocIds.slice();
    if (!ids.length) return;

    setRunError("");

    const indexed = indexedDocIdSetFrom(docs);
    const safeIds = ids.filter((id) => indexed.has(id));
    if (!safeIds.length) {
      setRunError("Selected docs are not indexed yet.");
      return;
    }

    const existing = new Set(runDocIds || []);
    const toAttach = safeIds.filter((id) => !existing.has(id));
    if (!toAttach.length) {
      setRunError("All selected docs are already attached to the current run.");
      return;
    }

    setRunBusy(true);
    clearAnswerAndDrill();
    try {
      if (typeof api.attachDocs === "function") {
        await api.attachDocs(runId, toAttach);
      } else {
        await attachDocsFallback(runId, toAttach);
      }
      await selectRun(runId);
      await refreshDocs();
    } catch (e) {
      setRunError(String(e?.message || e));
    } finally {
      setRunBusy(false);
    }
  }

  async function runAsk(modeOverride = null) {
    if (!hasToken) {
      setAskError("Set a demo token first.");
      return;
    }
    const docScopeId = !runId && selectedDocIds.length === 1 ? selectedDocIds[0] : null;
    if (!runId && !docScopeId) {
      setAskError("Select a run or exactly one document before asking.");
      return;
    }
    let prompt = (modeOverride ? question : question).trim();
    if (modeOverride === "summary_offline_safe" && !prompt) {
      prompt = "Provide a concise summary of this scope with key findings.";
      setQuestion((prev) => prev || prompt);
    }
    setAskBusy(true);
    setAskError("");
    clearAnswerAndDrill();
    try {
      const payload = { question: prompt || question, k: Number(k) || 6 };
      if (runId) {
        payload.run_id = runId;
      } else if (docScopeId) {
        payload.document_ids = [docScopeId];
      }
      if (modeOverride) {
        payload.mode = modeOverride;
      }
      const data = await api.ask(payload);
      setAnswerText(data.answer || "");
      setCitations(data.citations || []);
    } catch (e) {
      setAskError(String(e?.message || e));
    } finally {
      setAskBusy(false);
    }
  }

  async function getChunkWithFallback(chunkId, runIdMaybe) {
    try {
      return await api.getChunk(chunkId, runIdMaybe);
    } catch (e1) {
      const msg = String(e1?.message || e1);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        return await api.getChunk(chunkId, null);
      }
      throw e1;
    }
  }

  async function getDocPageChunksWithFallback(documentId, page, runIdMaybe) {
    try {
      return await api.getDocPageChunks(documentId, page, runIdMaybe);
    } catch (e1) {
      const msg = String(e1?.message || e1);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        return await api.getDocPageChunks(documentId, page, null);
      }
      throw e1;
    }
  }

  async function drill(cite) {
    if (!cite?.chunk_id) {
      // Guard to keep runtime safe even if API ever omits chunk metadata.
      setDrillError("Cannot drill this citation because chunk_id is unavailable.");
      return;
    }
    const chunkId = cite.chunk_id;
    setPdfPreviewEnabled(false);
    setPdfPreviewError("");
    setPdfPreviewBusy(false);
    if (pdfAbortRef.current) pdfAbortRef.current.abort();
    pdfAbortRef.current = null;
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    setPdfObjectUrl(null);

    setDrillBusy(true);
    setDrillError("");

    pageChunkRefs.current = new Map();

    const inferredDocId = cite?.document_id ?? resolveDocIdFromSourceId(cite?.source_id, docs) ?? null;
    setSelectedCitation({ ...cite, chunk_id: chunkId, document_id: inferredDocId });
    setSelectedChunk(null);
    setPageChunks([]);

    try {
      const chunk = await getChunkWithFallback(chunkId, runId || null);
      setSelectedChunk(chunk);

      if (chunk && (cite?.document_id == null || cite?.page == null)) {
        setSelectedCitation((prev) => ({
          ...prev,
          document_id: prev?.document_id ?? chunk.document_id ?? null,
          page: prev?.page ?? chunk.page ?? null,
        }));
      }

      if (chunk?.document_id != null && chunk?.page != null) {
        try {
          const pcs = await getDocPageChunksWithFallback(chunk.document_id, chunk.page, runId || null);
          setPageChunks(pcs || []);
        } catch (e2) {
          const p = Number(chunk.page);
          if (Number.isFinite(p)) {
            try {
              const pcs2 = await getDocPageChunksWithFallback(chunk.document_id, p + 1, runId || null);
              setPageChunks(pcs2 || []);
            } catch (e3) {
              try {
                const pcs3 = await getDocPageChunksWithFallback(chunk.document_id, Math.max(0, p - 1), runId || null);
                setPageChunks(pcs3 || []);
              } catch {
                throw e2;
              }
            }
          } else {
            throw e2;
          }
        }
      }
    } catch (e) {
      setDrillError(String(e?.message || e));
    } finally {
      setDrillBusy(false);
    }
  }

  // P04: pageChunks が描画された後に選択chunkへ自動スクロール
  useEffect(() => {
    const targetId = selectedCitation?.chunk_id;
    if (!targetId) return;
    if (!pageChunks?.length) return;

    const t = setTimeout(() => {
      const el = pageChunkRefs.current.get(targetId);
      if (el && typeof el.scrollIntoView === "function") {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        try {
          el.focus({ preventScroll: true });
        } catch {
          // noop
        }
      }
    }, 60);

    return () => clearTimeout(t);
  }, [selectedCitation?.chunk_id, pageChunks]);

  async function deleteRun(id) {
    const ok = window.prompt(`Type DELETE to remove run:\n${id}`) === "DELETE";
    if (!ok) return;

    try {
      await api.deleteRun(id);

      if (runId === id) {
        setRunId("");
        setRunDocIds([]);
        setRunConfigText("(none)");
        clearAnswerAndDrill();
      }
      await refreshRuns();
      await refreshDocs();
    } catch (e) {
      setRunsError(String(e?.message || e));
    }
  }

  async function cleanup(dryRun) {
    setCleanupBusy(true);
    setCleanupError("");
    setCleanupResult("(none)");
    try {
      const days = Math.max(1, Number(cleanupOlderDays) || 1);

      if (!dryRun) {
        const ok = window.prompt(`Type DELETE to execute cleanup.\nolder_than_days=${days}`) === "DELETE";
        if (!ok) return;
      }

      const result = await api.cleanupRuns({ older_than_days: days, dry_run: dryRun });
      setCleanupResult(JSON.stringify(result, null, 2));

      if (!dryRun) {
        await refreshRuns();
        await refreshDocs();
      }
    } catch (e) {
      setCleanupError(String(e?.message || e));
    } finally {
      setCleanupBusy(false);
    }
  }

  async function onUpload(file) {
    if (!hasToken) {
      setUploadResult("Set a demo token first.");
      return;
    }
    setUploadResult("Uploading...");
    try {
      const resp = await api.uploadPdf(file);
      setUploadResult(JSON.stringify(resp, null, 2));

      await refreshDocs();
      await refreshRuns();

      if (resp?.document_id && resp?.status !== "indexed") {
        setUploadResult(JSON.stringify({ ...resp, note: "Indexing... (polling /api/docs)" }, null, 2));
        const done = await waitUntilIndexed(resp.document_id);
        setUploadResult(JSON.stringify({ ...resp, polling: done }, null, 2));
        await refreshDocs();
      }
    } catch (e) {
      setUploadResult(String(e?.message || e));
    }
  }

  useEffect(() => {
    (async () => {
      try {
        await refreshDocs();
        await refreshRuns();
      } catch (e) {
        setUploadResult(`Init failed: ${String(e?.message || e)}`);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function enablePdfPreview() {
    setPdfPreviewError("");
    if (!drillDocId) {
      setPdfPreviewError("document_id is missing for preview.");
      return;
    }

    if (pdfAbortRef.current) pdfAbortRef.current.abort();
    pdfAbortRef.current = null;
    if (pdfObjectUrl) URL.revokeObjectURL(pdfObjectUrl);
    setPdfObjectUrl(null);

    setPdfPreviewEnabled(true);
    setPdfPreviewBusy(true);

    const controller = new AbortController();
    pdfAbortRef.current = controller;

    try {
      const objUrl = await fetchPdfAsObjectUrl(drillDocId, { signal: controller.signal });
      setPdfObjectUrl(objUrl);
    } catch (e) {
      setPdfPreviewError(String(e?.message || e));
      setPdfPreviewEnabled(false);
    } finally {
      setPdfPreviewBusy(false);
      pdfAbortRef.current = null;
    }
  }

  function openPdfInNewTab() {
    if (!drillDocId) return;
    const base = pdfViewUrl(drillDocId);
    const url = `${base}${pdfPageHash(drillPage)}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  // small helper for UI
  function filenameOf(docId) {
    if (!docId) return null;
    return (docs || []).find((d) => d.document_id === docId)?.filename || null;
  }

  return (
    <div className="container">
      <header className="header">
        <h1>RAG QA System</h1>
        <div className="muted" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={healthDotStyle(backendOk)} />
          <span>Backend:</span>
          <code>{API_BASE}</code>
          <span className="mono">{backendOk === null ? "checking" : backendOk ? "OK" : "NG"}</span>
          {backendMeta?.version ? <span className="mono">v{backendMeta.version}</span> : null}
          <span className="muted">
            LLM: <span className="mono">{llmStatusText}</span>
          </span>
        </div>
      </header>

      <section className="card">
        <h2>Connection / Demo Auth</h2>
        <div className="row gap" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <label className="label inline">Bearer token</label>
            <input
              type="password"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
              placeholder="Paste demo token"
            />
          </div>
          <button className="btnSmall" onClick={saveAuthToken}>
            Save
          </button>
          <button className="btnSmall" disabled={!hasToken} onClick={clearAuthToken}>
            Clear
          </button>
        </div>
        <div className="muted" style={{ marginTop: 4 }}>
          Current: <span className="mono">{hasToken ? `${savedToken.slice(0, 4)}…` : "(none)"}</span> — stored only in
          your browser (localStorage key <code>ragqa_token</code>).
        </div>
        {tokenStatus ? (
          <div className="muted" style={{ marginTop: 4 }}>
            {tokenStatus}
          </div>
        ) : null}
      </section>

      {/* Upload */}
      <section className="card">
        <h2>Upload PDF</h2>
        {!hasToken ? (
          <div className="error" style={{ marginBottom: 8 }}>
            Set a demo token above before uploading.
          </div>
        ) : null}
        <div className="row">
          <input
            type="file"
            accept="application/pdf"
            disabled={disableGlobal || !hasToken}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              if (!hasToken) {
                setUploadResult("Set a demo token first.");
                e.currentTarget.value = "";
                return;
              }
              if (!f.name.toLowerCase().endsWith(".pdf")) {
                setUploadResult("Only .pdf is allowed.");
                return;
              }
              void onUpload(f);
              e.currentTarget.value = "";
            }}
          />
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          Upload triggers background indexing. The list below will refresh automatically.
        </div>
        {llmWarning ? (
          <div className="muted" style={{ marginTop: 4 }}>
            Server LLM disabled; answers will use extractive summaries from retrieved chunks.
          </div>
        ) : null}
        <pre className="pre" style={{ marginTop: 10 }}>
          {uploadResult}
        </pre>
      </section>

      {/* Documents */}
      <section className="card">
        <div className="row space">
          <h2>Documents</h2>
          <button disabled={disableGlobal} onClick={() => void refreshDocs()}>
            Refresh
          </button>
        </div>

        <div className="muted">
          Count: {docs.length} / Indexed: {indexedDocIds.length}
        </div>

        <div className="row gap" style={{ alignItems: "flex-end", marginTop: 8 }}>
          <div className="muted" style={{ flex: 1 }}>
            Selected: <span className="mono">{selectedDocIds.length}</span> / Indexed selected:{" "}
            <span className="mono">{indexedSelectedCount}</span>
          </div>

          <button disabled={disableGlobal || indexedDocIds.length === 0} onClick={toggleSelectAllIndexed}>
            {allIndexedSelected ? "Unselect indexed" : "Select indexed"}
          </button>

          <button disabled={disableGlobal || selectedDocIds.length === 0} onClick={clearDocSelection}>
            Clear selection
          </button>

          <button
            disabled={disableGlobal || indexedSelectedCount === 0}
            onClick={() => void createRunFromSelectedDocs()}
            title="Create a new run with selected (indexed) docs"
          >
            Create Run (selected)
          </button>

          <button
            disabled={disableGlobal || indexedSelectedCount === 0 || !runId}
            onClick={() => void attachSelectedDocsToCurrentRun()}
            title={runId ? "Attach selected docs to current run" : "Select a run first"}
          >
            Attach to current run
          </button>
        </div>

        {runError ? (
          <div className="error" style={{ marginTop: 8 }}>
            {runError}
          </div>
        ) : null}

        <div style={{ marginTop: 10 }}>
          {docs.map((d) => {
            const active = docsHighlightSet.has(d.document_id);
            const checked = selectedDocSet.has(d.document_id);
            const isIndexed = d.status === "indexed";

            return (
              <div
                key={d.document_id}
                className="doc"
                style={{
                  ...(active ? { outline: "2px solid rgba(127,127,127,.55)" } : {}),
                  ...(checked ? { background: "rgba(127,127,127,.08)" } : {}),
                }}
              >
                <div className="docMain">
                  <div className="row gap" style={{ alignItems: "flex-start" }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disableGlobal}
                      onChange={() => toggleDocSelect(d.document_id)}
                      style={{ marginTop: 6 }}
                      title={isIndexed ? "Select this document" : "Select (not indexed yet)"}
                    />

                    <div style={{ flex: 1 }}>
                      <div className="docTitle">{d.filename}</div>
                      <div className="muted">
                        <span className="badge">{d.status}</span> <span className="mono">{d.document_id}</span>
                      </div>
                      {d.error ? <div className="error">Error: {d.error}</div> : null}
                    </div>
                  </div>
                </div>

                <div className="docActions">
                  <a
                    className="btnLink"
                    href={`${API_BASE}/docs/${d.document_id}/download`}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Download
                  </a>

                  <a
                    className="btnLink"
                    href={`${API_BASE}/docs/${d.document_id}/view`}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    title="Open inline view (no download)"
                    style={{ marginLeft: 8 }}
                  >
                    View
                  </a>

                  <button className="btnSmall" disabled={disableGlobal} onClick={() => void safeCopy(d.document_id)}>
                    Copy ID
                  </button>
                  <button
                    className="btnSmall"
                    disabled={!isIndexed || disableGlobal}
                    title={isIndexed ? "" : "Index completed docs only"}
                    onClick={() => void createRunForDoc(d.document_id)}
                  >
                    Create Run
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Runs */}
      <section className="card">
        <div className="row space">
          <h2>Runs</h2>
          <button disabled={disableGlobal} onClick={() => void refreshRuns()}>
            Refresh
          </button>
        </div>

        <div className="divider" />

        <div className="row gap" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 200 }}>
            <label className="label inline">Cleanup older_than_days</label>
            <input
              type="number"
              min={1}
              max={365}
              value={cleanupOlderDays}
              disabled={disableGlobal}
              onChange={(e) => setCleanupOlderDays(Number(e.target.value))}
            />
          </div>
          <button disabled={disableGlobal} onClick={() => void cleanup(true)}>
            Dry-run
          </button>
          <button disabled={disableGlobal} onClick={() => void cleanup(false)}>
            Execute
          </button>
          <div className="muted" style={{ flex: 1 }}>
            ※ Execute は “DELETE” 入力が必要（安全装置）
          </div>
        </div>

        {cleanupError ? <div className="error">{cleanupError}</div> : null}
        <details style={{ marginTop: 10 }}>
          <summary>Cleanup result (debug)</summary>
          <pre className="pre">{cleanupResult}</pre>
        </details>

        <div className="divider" />

        <div className="muted">Count: {runs.length}</div>
        {runsError ? <div className="error">{runsError}</div> : null}

        <div>
          {runs.map((r) => {
            const selected = runId === r.run_id;
            return (
              <div
                key={r.run_id}
                className="doc"
                style={selected ? { outline: "2px solid rgba(127,127,127,.75)" } : {}}
              >
                <div className="docMain">
                  <div className="docTitle">Run</div>
                  <div className="muted">
                    <span className="badge">{r.status}</span> <span className="mono">{r.run_id}</span>
                  </div>
                  <div className="muted">
                    created_at: <span className="mono">{r.created_at}</span> / docs: {r.document_ids?.length ?? 0}
                  </div>
                </div>
                <div className="docActions">
                  <button className="btnSmall" disabled={disableGlobal} onClick={() => void selectRun(r.run_id)}>
                    Use
                  </button>
                  <button className="btnSmall" disabled={disableGlobal} onClick={() => void safeCopy(r.run_id)}>
                    Copy
                  </button>
                  <button className="btnSmall" disabled={disableGlobal} onClick={() => void deleteRun(r.run_id)}>
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Run & Ask */}
      <section className="card">
        <h2>Run & Ask</h2>

        <div className="row gap">
          <div className="pill">
            Run ID: <span className="mono">{runId || "(none)"}</span>
          </div>
          <div className="pill">
            Doc IDs: <span className="mono">{formatDocIds(runDocIds)}</span>
          </div>
          <div className="pill">
            Scope: <span className="mono">{scopeLabel}</span>
          </div>
          <button className="btnSmall" disabled={!runId || disableGlobal} onClick={() => runId && void safeCopy(runId)}>
            Copy Run ID
          </button>
        </div>

        <details style={{ marginTop: 10 }}>
          <summary>Run config (debug)</summary>
          <pre className="pre">{runConfigText}</pre>
        </details>

        <label className="label">Question</label>
        <textarea value={question} disabled={disableGlobal} onChange={(e) => setQuestion(e.target.value)} />
        {llmWarning ? (
          <div className="muted" style={{ marginTop: 8 }}>
            Server LLM offline &mdash; Ask responses will be generated from retrieved text snippets.
          </div>
        ) : null}

        <div className="row gap" style={{ marginTop: 10 }}>
          <div style={{ width: 120 }}>
            <label className="label inline">k</label>
            <input
              type="number"
              min={1}
              max={50}
              value={k}
              disabled={disableGlobal}
              onChange={(e) => setK(Number(e.target.value))}
            />
          </div>

          <button className="primary" disabled={askDisabled} onClick={() => void runAsk()}>
            Ask
          </button>
          <button
            className="btnSmall"
            disabled={askDisabled}
            onClick={() => void runAsk("summary_offline_safe")}
            title="Uses deterministic context + extractive fallback when LLM is offline."
          >
            Summary (offline-safe)
          </button>

          <div className="muted" style={{ flex: 1 }}>
            {!hasToken
              ? "Set a demo token to enable Ask."
              : runId
              ? "※ Ask を有効にするには Run を選択してね"
              : singleDocScopeId
              ? "Using selected document scope."
              : "Select a run or exactly one document to enable Ask."}
          </div>
        </div>

        {askError ? <div className="error">{askError}</div> : null}

        {answerText ? (
          <div style={{ marginTop: 12 }}>
            <h3>Answer</h3>
            <pre className="pre">{answerText}</pre>

            <h3>Citations</h3>
            <div className="citations">
              {citations.map((c, idx) => {
                const chunkId = c?.chunk_id ?? null;
                const docId = c?.document_id ?? resolveDocIdFromSourceId(c?.source_id, docs) ?? null;
                const fn = filenameOf(docId);
                const drilldownBlockedReason = c?.drilldown_blocked_reason ?? null;
                const canDrill = Boolean(chunkId) && !drilldownBlockedReason;
                const chunkMissingReasonRaw = c?.chunk_id_missing_reason;
                const chunkMissingReason = !canDrill
                  ? chunkMissingReasonRaw
                    ? `Chunk unavailable: ${chunkMissingReasonRaw}`
                    : drilldownBlockedReason
                    ? `Drilldown disabled: ${drilldownBlockedReason}`
                    : "Chunk reference unavailable."
                  : null;
                const citeKey = `${chunkId ?? `nochunk-${idx}`}-${c?.source_id ?? "S"}-${idx}`;
                const citeClass = canDrill ? "citeItem" : "citeItem disabled";
                const pdfEnabled = Boolean(docId) && canDrill;
                const pdfDisabledTitle = !canDrill
                  ? chunkMissingReason || "chunk_id unavailable"
                  : "document_id is unavailable";

                return (
                  <div
                    key={citeKey}
                    className={citeClass}
                    onClick={canDrill ? () => void drill(c) : undefined}
                    role={canDrill ? "button" : undefined}
                    tabIndex={canDrill ? 0 : -1}
                    onKeyDown={
                      canDrill
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") void drill(c);
                          }
                        : undefined
                    }
                  >
                    <div className="citeTitle">
                      <div>
                        <strong>[{c.source_id}]</strong>{" "}
                        {fn ? <span className="muted" style={{ marginLeft: 6 }}>{fn}</span> : null}
                      </div>
                      <div className="mono">page {c.page}</div>
                    </div>

                    <div className="citeMeta mono">{chunkId || "(chunk unavailable)"}</div>
                    {!canDrill && chunkMissingReason ? <div className="citeWarning">{chunkMissingReason}</div> : null}

                    <div className="citeLinks">
                      <button
                        className="btnSmall"
                        disabled={!pdfEnabled}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!pdfEnabled) return;
                          const url = `${pdfViewUrl(docId)}${pdfPageHash(c.page)}`;
                          window.open(url, "_blank", "noopener,noreferrer");
                        }}
                        title={pdfEnabled ? "Open the PDF inline at the cited page" : pdfDisabledTitle}
                      >
                        Open PDF
                      </button>

                      <button
                        className="btnSmall"
                        disabled={!pdfEnabled}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!pdfEnabled) return;
                          const url = `${pdfDownloadUrl(docId)}${pdfPageHash(c.page)}`;
                          window.open(url, "_blank", "noopener,noreferrer");
                        }}
                        title={pdfEnabled ? "Download the PDF at the cited page" : pdfDisabledTitle}
                        style={{ marginLeft: 8 }}
                      >
                        Download
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>

      {/* Drilldown */}
      {selectedCitation ? (
        <section className="card">
          <h2>Drilldown</h2>
          {drillError ? <div className="error">{drillError}</div> : null}

          <div className="row gap">
            <div className="pill">
              Selected:{" "}
              <span className="mono">
                {selectedCitation.source_id} / page {selectedCitation.page}
              </span>
            </div>
          </div>

          <div style={{ marginTop: 10 }}>
            <div className="row gap" style={{ alignItems: "center" }}>
              <div className="muted" style={{ flex: 1 }}>
                Evidence PDF:{" "}
                <span className="mono">{drillDocId ? drillDocId : "(unresolved)"}</span>
                {drillDocId && filenameOf(drillDocId) ? (
                  <span className="muted" style={{ marginLeft: 6 }}>
                    ({filenameOf(drillDocId)})
                  </span>
                ) : null}
                {" / "}page {normalizePdfPage(drillPage)}
              </div>

              <button
                className="btnSmall"
                disabled={!drillDocId || pdfPreviewBusy}
                onClick={() => void enablePdfPreview()}
                title={!drillDocId ? "document_id not resolved yet" : "Fetch /view as blob and preview"}
              >
                {pdfPreviewBusy ? "Loading PDF..." : "Preview PDF"}
              </button>

              <button
                className="btnSmall"
                disabled={!drillDocId}
                onClick={openPdfInNewTab}
                title={!drillDocId ? "document_id not resolved yet" : "Open /view in new tab"}
              >
                Open in new tab
              </button>

              <button
                className="btnSmall"
                disabled={!drillDocId}
                onClick={() => {
                  if (!drillDocId) return;
                  const url = `${pdfDownloadUrl(drillDocId)}${pdfPageHash(drillPage)}`;
                  window.open(url, "_blank", "noopener,noreferrer");
                }}
                title={!drillDocId ? "document_id not resolved yet" : "Open /download in new tab"}
              >
                Download
              </button>
            </div>

            {pdfPreviewError ? <div className="error" style={{ marginTop: 8 }}>{pdfPreviewError}</div> : null}

            {pdfPreviewEnabled && drillPdfIframeSrc ? (
              <iframe className="pdfFrame" title="PDF preview" src={drillPdfIframeSrc} />
            ) : null}

            {!pdfPreviewEnabled ? (
              <div className="muted" style={{ marginTop: 8 }}>
                ※ クリックだけでPDFが落ちるのを防ぐため、プレビューは手動表示です（/view を使用）。
              </div>
            ) : null}
          </div>

          <h3>Chunk</h3>
          <pre className="pre">{selectedChunk ? selectedChunk.text : drillBusy ? "Loading..." : ""}</pre>

          <h3>Same page chunks</h3>
          <div>
            {pageChunks.map((pc) => {
              const hit = selectedCitation?.chunk_id === pc.chunk_id;
              return (
                <div
                  key={pc.chunk_id}
                  className={`pageChunk ${hit ? "highlight" : ""}`}
                  tabIndex={-1}
                  ref={(el) => {
                    if (!el) return;
                    pageChunkRefs.current.set(pc.chunk_id, el);
                  }}
                >
                  <div className="row space">
                    <div className="mono">chunk_index: {pc.chunk_index}</div>
                    <div className="mono">{pc.chunk_id}</div>
                  </div>
                  <div className="divider"></div>
                  <div className="mono" style={{ whiteSpace: "pre-wrap" }}>
                    {pc.text}
                  </div>
                </div>
              );
            })}
            {!pageChunks.length && !drillBusy ? (
              <div className="muted" style={{ marginTop: 8 }}>
                (no chunks on this page or not found)
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
