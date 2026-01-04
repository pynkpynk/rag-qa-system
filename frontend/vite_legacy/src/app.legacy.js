const API_BASE = "/api";
const $ = (sel) => document.querySelector(sel);

const state = {
  // Docs
  docs: [],

  // Runs
  runs: [],
  runsBusy: false,
  runsError: "",

  // Runs cleanup UI
  cleanupOlderThanDays: 1,
  cleanupDryRunResult: null, // {dry_run, cutoff_utc, candidates, ...}
  cleanupBusy: false,
  cleanupError: "",

  // Selected Run
  runId: "",
  runDocIds: [], // ← 複数docを想定
  runConfig: null,
  runBusy: false,
  runError: "",

  // Ask
  question: "What is the P1 response time target for the Pro plan? Answer with citations.",
  k: 6,
  askBusy: false,
  askError: "",
  answerText: "",
  citations: [],

  // Drilldown
  drillBusy: false,
  drillError: "",
  selectedCitation: null, // {source_id, chunk_id, page, document_id}
  selectedChunk: null,    // /chunks/{chunk_id} response
  pageChunks: [],         // /docs/{doc}/pages/{page} response
};

let mounted = false;

/* =========================
 * Utils
 * ========================= */
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function qs(params) {
  const u = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);

  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const ct = res.headers.get("content-type") || "";
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
  const t = await res.text().catch(() => "");
  return { raw: t };
}

/* =========================
 * API
 * ========================= */
async function apiListDocs() {
  return fetchJson(`${API_BASE}/docs`);
}

async function apiUploadPdf(file) {
  const fd = new FormData();
  fd.append("file", file);
  return fetchJson(`${API_BASE}/docs/upload`, { method: "POST", body: fd });
}

async function apiCreateRun(payload) {
  return fetchJson(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function apiListRuns() {
  return fetchJson(`${API_BASE}/runs`);
}

async function apiGetRun(runId) {
  return fetchJson(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
}

// 単体削除: DELETE /api/runs/{run_id}?confirm=DELETE
async function apiDeleteRun(runId) {
  return fetchJson(`${API_BASE}/runs/${encodeURIComponent(runId)}${qs({ confirm: "DELETE" })}`, {
    method: "DELETE",
  });
}

// 一括cleanup: DELETE /api/runs?older_than_days=N&dry_run=true|false&confirm=DELETE
async function apiCleanupRuns({ olderThanDays, dryRun }) {
  const params = {
    older_than_days: Number(olderThanDays) || 1,
    dry_run: dryRun ? "true" : "false",
  };
  if (!dryRun) params.confirm = "DELETE";

  return fetchJson(`${API_BASE}/runs${qs(params)}`, { method: "DELETE" });
}

async function apiAsk(payload) {
  return fetchJson(`${API_BASE}/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function apiGetChunk(chunkId, runId = null) {
  return fetchJson(`${API_BASE}/chunks/${encodeURIComponent(chunkId)}${qs({ run_id: runId })}`);
}

async function apiGetDocPageChunks(documentId, page, runId = null) {
  return fetchJson(
    `${API_BASE}/docs/${encodeURIComponent(documentId)}/pages/${encodeURIComponent(page)}${qs({ run_id: runId })}`
  );
}

/* =========================
 * Render (Shell)
 * ========================= */
function renderShell() {
  $("#app").innerHTML = `
    <div class="container">
      <header class="header">
        <h1>RAG QA System</h1>
        <div class="muted">Backend: <code>${API_BASE}</code></div>
      </header>

      <section class="card">
        <h2>Upload PDF</h2>
        <form id="uploadForm" class="row">
          <input id="pdfFile" type="file" accept="application/pdf" />
          <button id="uploadBtn" type="submit">Upload</button>
        </form>
        <div id="uploadHint" class="muted">
          Upload triggers background indexing. The list below will refresh automatically.
        </div>
        <pre id="uploadResult" class="pre"></pre>
      </section>

      <section class="card">
        <div class="row space">
          <h2>Documents</h2>
          <button id="refreshBtn" type="button">Refresh</button>
        </div>
        <div id="docsMeta" class="muted"></div>
        <div id="docsList"></div>
      </section>

      <section class="card">
        <div class="row space">
          <h2>Runs</h2>
          <div class="row gap">
            <button id="refreshRunsBtn" type="button">Refresh</button>
          </div>
        </div>

        <!-- Cleanup UI -->
        <div class="divider"></div>
        <div class="row gap" style="align-items:flex-end;">
          <div style="width:180px;">
            <label class="label inline" for="olderDaysInput">Cleanup older_than_days</label>
            <input id="olderDaysInput" type="number" min="1" max="365" value="${escapeHtml(state.cleanupOlderThanDays)}" />
          </div>
          <button id="dryRunBtn" type="button">Dry-run</button>
          <button id="execCleanupBtn" type="button">Execute</button>
          <div class="muted" style="flex:1;">
            ※ Execute は確認が出ます（安全装置）
          </div>
        </div>
        <div id="cleanupError" class="error"></div>
        <details style="margin-top:10px;">
          <summary>Cleanup result (debug)</summary>
          <pre class="pre" id="cleanupPre"></pre>
        </details>

        <div class="divider"></div>

        <div id="runsMeta" class="muted"></div>
        <div id="runsError" class="error"></div>
        <div id="runsList"></div>
      </section>

      <section class="card">
        <h2>Run & Ask</h2>

        <div class="row gap">
          <div class="pill">Run ID: <span class="mono" id="runIdText">(none)</span></div>
          <div class="pill">Doc IDs: <span class="mono" id="runDocsText">(none)</span></div>
          <button id="copyRunBtn" class="btnSmall" type="button" disabled>Copy Run ID</button>
        </div>

        <details style="margin-top:10px;">
          <summary>Run config (debug)</summary>
          <pre class="pre" id="runConfigPre"></pre>
        </details>

        <div id="runError" class="error"></div>

        <label class="label" for="questionInput">Question</label>
        <textarea id="questionInput"></textarea>

        <div class="row gap" style="margin-top:10px;">
          <div style="width:120px;">
            <label class="label inline" for="kInput">k</label>
            <input id="kInput" type="number" min="1" max="50" />
          </div>
          <button id="askBtn" class="primary" type="button" disabled>Ask</button>
          <div class="muted" style="flex:1;">
            ※ Ask を有効にするには、Docs の「Create Run」または Runs の「Use」を押して Run を選択してね
          </div>
        </div>

        <div id="askError" class="error"></div>

        <div id="answerBlock" style="margin-top:12px; display:none;">
          <h3>Answer</h3>
          <pre class="pre" id="answerText"></pre>

          <h3>Citations</h3>
          <div class="citations" id="citationsList"></div>
        </div>
      </section>

      <section class="card" id="drillCard" style="display:none;">
        <h2>Drilldown</h2>
        <div id="drillError" class="error"></div>

        <div class="row gap">
          <div class="pill">Selected: <span class="mono" id="selCiteText"></span></div>
        </div>

        <h3>Chunk</h3>
        <pre class="pre" id="chunkText"></pre>

        <h3>Same page chunks</h3>
        <div class="pageChunks" id="pageChunksList"></div>
      </section>
    </div>
  `;
}

/* =========================
 * Render (Parts)
 * ========================= */
function renderDocs(docs) {
  state.docs = docs;

  $("#docsMeta").textContent = `Count: ${docs.length}`;
  $("#docsList").innerHTML = docs
    .map((d) => {
      const id = escapeHtml(d.document_id);
      const filename = escapeHtml(d.filename);
      const status = escapeHtml(d.status);
      const err = d.error ? `<div class="error">Error: ${escapeHtml(d.error)}</div>` : "";

      const isIndexed = d.status === "indexed";
      const isActive = state.runDocIds?.includes(d.document_id);

      return `
        <div class="doc" style="${isActive ? "outline:2px solid rgba(127,127,127,.55);" : ""}">
          <div class="docMain">
            <div class="docTitle">${filename}</div>
            <div class="muted">
              <span class="badge">${status}</span>
              <span class="mono">${id}</span>
            </div>
            ${err}
          </div>
          <div class="docActions">
            <a class="btnLink" href="${API_BASE}/docs/${id}/download" target="_blank" rel="noreferrer">Download</a>
            <button class="btnSmall" data-copy="${id}">Copy ID</button>
            <button class="btnSmall" data-run="${id}" ${isIndexed ? "" : "disabled"} title="${isIndexed ? "" : "Index completed docs only"}">
              Create Run
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  // Copy doc id
  $("#docsList").querySelectorAll("button[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-copy");
      try {
        await navigator.clipboard.writeText(id);
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = "Copy ID"), 900);
      } catch {
        window.prompt("Copy this ID:", id);
      }
    });
  });

  // Create run
  $("#docsList").querySelectorAll("button[data-run]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const docId = btn.getAttribute("data-run");
      await createRunForDoc(docId);
    });
  });
}

function renderRuns(runs) {
  state.runs = runs;

  $("#runsMeta").textContent = `Count: ${runs.length}`;
  $("#runsError").textContent = state.runsError || "";
  $("#cleanupError").textContent = state.cleanupError || "";
  $("#cleanupPre").textContent = state.cleanupDryRunResult
    ? JSON.stringify(state.cleanupDryRunResult, null, 2)
    : "(none)";

  $("#runsList").innerHTML = runs
    .map((r) => {
      const runId = escapeHtml(r.run_id);
      const createdAt = escapeHtml(r.created_at);
      const status = escapeHtml(r.status || "");
      const docCount = Array.isArray(r.document_ids) ? r.document_ids.length : 0;

      const isSelected = state.runId === r.run_id;

      return `
        <div class="doc" style="${isSelected ? "outline:2px solid rgba(127,127,127,.75);" : ""}">
          <div class="docMain">
            <div class="docTitle">Run</div>
            <div class="muted">
              <span class="badge">${status}</span>
              <span class="mono">${runId}</span>
            </div>
            <div class="muted">created_at: <span class="mono">${createdAt}</span> / docs: ${docCount}</div>
          </div>
          <div class="docActions">
            <button class="btnSmall" data-use-run="${runId}">Use</button>
            <button class="btnSmall" data-copy-run="${runId}">Copy</button>
            <button class="btnSmall" data-del-run="${runId}">Delete</button>
          </div>
        </div>
      `;
    })
    .join("");

  $("#runsList").querySelectorAll("button[data-copy-run]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-copy-run");
      try {
        await navigator.clipboard.writeText(id);
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = "Copy"), 900);
      } catch {
        window.prompt("Copy this Run ID:", id);
      }
    });
  });

  $("#runsList").querySelectorAll("button[data-use-run]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-use-run");
      await selectRun(id);
    });
  });

  $("#runsList").querySelectorAll("button[data-del-run]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-del-run");
      await deleteRun(id);
    });
  });
}

function formatDocIds(docIds) {
  if (!Array.isArray(docIds) || docIds.length === 0) return "(none)";
  if (docIds.length <= 2) return docIds.join(", ");
  return `${docIds.length} doc(s): ${docIds[0]}, ${docIds[1]}, ...`;
}

function renderRunAsk() {
  $("#runIdText").textContent = state.runId || "(none)";
  $("#runDocsText").textContent = formatDocIds(state.runDocIds);
  $("#copyRunBtn").disabled = !state.runId;

  $("#runConfigPre").textContent = state.runConfig ? JSON.stringify(state.runConfig, null, 2) : "(none)";

  $("#runError").textContent = state.runError || "";
  $("#askError").textContent = state.askError || "";

  $("#questionInput").value = state.question;
  $("#kInput").value = String(state.k);

  $("#askBtn").disabled = !state.runId || state.askBusy || state.runBusy;

  // Answer
  const hasAnswer = Boolean(state.answerText);
  $("#answerBlock").style.display = hasAnswer ? "block" : "none";
  if (hasAnswer) {
    $("#answerText").textContent = state.answerText;

    $("#citationsList").innerHTML = (state.citations || [])
      .map((c) => {
        const sid = escapeHtml(c.source_id);
        const chunkId = escapeHtml(c.chunk_id);
        const page = escapeHtml(c.page);
        const docId = escapeHtml(c.document_id);
        return `
          <div class="citeItem" data-chunk="${chunkId}" data-page="${page}" data-doc="${docId}" data-sid="${sid}">
            <div class="citeTitle">
              <div><strong>[${sid}]</strong></div>
              <div class="mono">page ${page}</div>
            </div>
            <div class="citeMeta mono">${chunkId}</div>
          </div>
        `;
      })
      .join("");

    $("#citationsList").querySelectorAll(".citeItem").forEach((el) => {
      el.addEventListener("click", async () => {
        const chunkId = el.getAttribute("data-chunk");
        const page = Number(el.getAttribute("data-page"));
        const docId = el.getAttribute("data-doc");
        const sid = el.getAttribute("data-sid") || "S?";
        await drilldownCitation({ source_id: sid, chunk_id: chunkId, page, document_id: docId });
      });
    });
  }

  // Drilldown
  const showDrill = Boolean(state.selectedCitation);
  $("#drillCard").style.display = showDrill ? "block" : "none";
  if (showDrill) {
    $("#drillError").textContent = state.drillError || "";
    $("#selCiteText").textContent = `${state.selectedCitation.source_id} / page ${state.selectedCitation.page}`;

    $("#chunkText").textContent = state.selectedChunk
      ? state.selectedChunk.text
      : (state.drillBusy ? "Loading..." : "");

    $("#pageChunksList").innerHTML = (state.pageChunks || [])
      .map((pc) => {
        const chunkId = pc.chunk_id;
        const isHit = state.selectedCitation?.chunk_id === chunkId;
        return `
          <div class="pageChunk ${isHit ? "highlight" : ""}">
            <div class="row space">
              <div class="mono">chunk_index: ${escapeHtml(pc.chunk_index)}</div>
              <div class="mono">${escapeHtml(pc.chunk_id)}</div>
            </div>
            <div class="divider"></div>
            <div class="mono" style="white-space:pre-wrap;">${escapeHtml(pc.text)}</div>
          </div>
        `;
      })
      .join("");
  }

  // Cleanup buttons state
  const disableCleanup = state.cleanupBusy || state.runsBusy || state.runBusy || state.askBusy;
  $("#dryRunBtn").disabled = disableCleanup;
  $("#execCleanupBtn").disabled = disableCleanup;
  $("#olderDaysInput").disabled = disableCleanup;

  // Runs refresh button state
  $("#refreshRunsBtn").disabled = state.runsBusy || state.cleanupBusy;
}

function ensureMounted() {
  if (mounted) return;
  renderShell();
  wireEvents();
  mounted = true;
}

function renderAllParts() {
  ensureMounted();
  renderDocs(state.docs || []);
  renderRuns(state.runs || []);
  renderRunAsk();
}

/* =========================
 * Logic
 * ========================= */
async function refreshDocs() {
  const docs = await apiListDocs();
  state.docs = docs;
  renderAllParts();
  return docs;
}

async function refreshRuns() {
  state.runsBusy = true;
  state.runsError = "";
  renderAllParts();
  try {
    const runs = await apiListRuns();
    state.runs = runs;
  } catch (e) {
    state.runsError = String(e?.message || e);
  } finally {
    state.runsBusy = false;
    renderAllParts();
  }
}

async function waitUntilIndexed(targetDocId, { intervalMs = 1000, timeoutMs = 60000 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const docs = await apiListDocs();
    state.docs = docs;
    renderAllParts();

    const hit = docs.find((d) => d.document_id === targetDocId);
    if (!hit) return { done: true, status: "missing" };
    if (hit.status === "indexed") return { done: true, status: "indexed" };
    if (hit.status === "failed") return { done: true, status: "failed", error: hit.error };
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return { done: false, status: "timeout" };
}

function defaultRunConfig() {
  return {
    model: "gpt-5-mini",
    chunk: { size: 800, overlap: 120 },
    retriever: { k: 8 },
  };
}

function clearAnswerAndDrill() {
  state.askError = "";
  state.answerText = "";
  state.citations = [];
  state.selectedCitation = null;
  state.selectedChunk = null;
  state.pageChunks = [];
  state.drillError = "";
}

async function selectRun(runId) {
  state.runBusy = true;
  state.runError = "";
  clearAnswerAndDrill();
  renderAllParts();

  try {
    const data = await apiGetRun(runId);
    state.runId = data.run_id;
    state.runDocIds = Array.isArray(data.document_ids) ? data.document_ids : [];
    state.runConfig = data.config || null;
  } catch (e) {
    state.runError = String(e?.message || e);
  } finally {
    state.runBusy = false;
    renderAllParts();
  }
}

async function createRunForDoc(documentId) {
  state.runBusy = true;
  state.runError = "";
  clearAnswerAndDrill();
  renderAllParts();

  try {
    const payload = { config: defaultRunConfig(), document_ids: [documentId] };
    const data = await apiCreateRun(payload);

    await selectRun(data.run_id);
    await refreshRuns();
  } catch (e) {
    state.runError = String(e?.message || e);
  } finally {
    state.runBusy = false;
    renderAllParts();
  }
}

async function askQuestion() {
  if (!state.runId) {
    state.askError = "Run ID is missing. Create or select a run first.";
    renderAllParts();
    return;
  }

  state.askBusy = true;
  state.askError = "";
  clearAnswerAndDrill();
  renderAllParts();

  try {
    const payload = {
      question: state.question,
      k: Number(state.k) || 6,
      run_id: state.runId,
    };
    const data = await apiAsk(payload);
    state.answerText = data.answer || "";
    state.citations = data.citations || [];
  } catch (e) {
    state.askError = String(e?.message || e);
  } finally {
    state.askBusy = false;
    renderAllParts();
  }
}

async function drilldownCitation(cite) {
  state.drillBusy = true;
  state.drillError = "";
  state.selectedCitation = cite;
  state.selectedChunk = null;
  state.pageChunks = [];
  renderAllParts();

  try {
    const chunk = await apiGetChunk(cite.chunk_id, state.runId);
    state.selectedChunk = chunk;

    if (chunk?.document_id != null && chunk?.page != null) {
      state.pageChunks = await apiGetDocPageChunks(chunk.document_id, chunk.page, state.runId);
    }
  } catch (e) {
    state.drillError = String(e?.message || e);
  } finally {
    state.drillBusy = false;
    renderAllParts();
  }
}

async function deleteRun(runId) {
  const ok = window.prompt(`Type DELETE to remove run:\n${runId}`) === "DELETE";
  if (!ok) return;

  state.runsError = "";
  state.runError = "";
  state.cleanupError = "";
  state.cleanupDryRunResult = null;
  renderAllParts();

  try {
    await apiDeleteRun(runId);

    // 選択中runが消えたら解除
    if (state.runId === runId) {
      state.runId = "";
      state.runDocIds = [];
      state.runConfig = null;
      clearAnswerAndDrill();
    }

    await refreshRuns();
    await refreshDocs(); // 見た目のハイライト整合のため
  } catch (e) {
    state.runsError = String(e?.message || e);
  } finally {
    renderAllParts();
  }
}

async function cleanupRuns({ dryRun }) {
  state.cleanupBusy = true;
  state.cleanupError = "";
  state.cleanupDryRunResult = null;
  renderAllParts();

  try {
    if (!dryRun) {
      const ok = window.prompt(
        `Type DELETE to execute cleanup.\nolder_than_days=${state.cleanupOlderThanDays}`
      ) === "DELETE";
      if (!ok) return;
    }

    const data = await apiCleanupRuns({
      olderThanDays: state.cleanupOlderThanDays,
      dryRun,
    });

    state.cleanupDryRunResult = data;

    // 実行後はrunsを更新、選択runが消えた可能性もあるので整合を取る
    if (!dryRun) {
      await refreshRuns();

      const stillExists = state.runId && state.runs.some((r) => r.run_id === state.runId);
      if (!stillExists) {
        state.runId = "";
        state.runDocIds = [];
        state.runConfig = null;
        clearAnswerAndDrill();
      }
      await refreshDocs();
    }
  } catch (e) {
    state.cleanupError = String(e?.message || e);
  } finally {
    state.cleanupBusy = false;
    renderAllParts();
  }
}

/* =========================
 * Events
 * ========================= */
function setUploadBusy(isBusy) {
  $("#uploadBtn").disabled = isBusy;
  $("#refreshBtn").disabled = isBusy;
  $("#refreshRunsBtn").disabled = isBusy;
  $("#pdfFile").disabled = isBusy;
}

function showUploadResult(objOrText) {
  const text = typeof objOrText === "string" ? objOrText : JSON.stringify(objOrText, null, 2);
  $("#uploadResult").textContent = text;
}

function wireEvents() {
  // Refresh docs
  $("#refreshBtn").addEventListener("click", async () => {
    try {
      $("#refreshBtn").textContent = "Refreshing...";
      await refreshDocs();
    } finally {
      $("#refreshBtn").textContent = "Refresh";
    }
  });

  // Refresh runs
  $("#refreshRunsBtn").addEventListener("click", async () => {
    try {
      $("#refreshRunsBtn").textContent = "Refreshing...";
      await refreshRuns();
    } finally {
      $("#refreshRunsBtn").textContent = "Refresh";
    }
  });

  // Cleanup inputs/buttons
  $("#olderDaysInput").addEventListener("input", (e) => {
    state.cleanupOlderThanDays = Number(e.target.value) || 1;
  });

  $("#dryRunBtn").addEventListener("click", async () => {
    await cleanupRuns({ dryRun: true });
  });

  $("#execCleanupBtn").addEventListener("click", async () => {
    await cleanupRuns({ dryRun: false });
  });

  // Upload
  $("#uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const file = $("#pdfFile").files?.[0];
    if (!file) {
      showUploadResult("Pick a PDF file first.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showUploadResult("Only .pdf is allowed.");
      return;
    }

    setUploadBusy(true);
    showUploadResult("Uploading...");

    try {
      const resp = await apiUploadPdf(file);
      showUploadResult(resp);

      await refreshDocs();

      if (resp?.document_id && resp?.status !== "indexed") {
        showUploadResult({ ...resp, note: "Indexing... (polling /api/docs)" });
        const done = await waitUntilIndexed(resp.document_id);
        showUploadResult({ ...resp, polling: done });
        await refreshDocs();
      }
    } catch (err) {
      showUploadResult(String(err?.message || err));
    } finally {
      setUploadBusy(false);
      $("#pdfFile").value = "";
    }
  });

  // Run copy (selected)
  $("#copyRunBtn").addEventListener("click", async () => {
    if (!state.runId) return;
    try {
      await navigator.clipboard.writeText(state.runId);
      $("#copyRunBtn").textContent = "Copied";
      setTimeout(() => ($("#copyRunBtn").textContent = "Copy Run ID"), 900);
    } catch {
      window.prompt("Copy this Run ID:", state.runId);
    }
  });

  // Ask inputs
  $("#questionInput").addEventListener("input", (e) => {
    state.question = e.target.value;
  });

  $("#kInput").addEventListener("input", (e) => {
    state.k = e.target.value;
  });

  // Ask
  $("#askBtn").addEventListener("click", async () => {
    await askQuestion();
  });
}

/* =========================
 * Boot
 * ========================= */
async function main() {
  ensureMounted();
  renderAllParts();
  try {
    await refreshDocs();
    await refreshRuns();
  } catch (e) {
    showUploadResult(`Init failed: ${String(e?.message || e)}`);
  }
}

main();
