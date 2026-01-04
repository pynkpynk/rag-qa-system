const API_BASE = "/api";

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

  // 204対策
  if (res.status === 204) return null;

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
    } catch {}
    throw new Error(msg);
  }

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  const t = await res.text().catch(() => "");
  return { raw: t };
}

export const api = {
  // Docs
  listDocs: () => fetchJson(`${API_BASE}/docs`),
  uploadPdf: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetchJson(`${API_BASE}/docs/upload`, { method: "POST", body: fd });
  },

  // Runs
  listRuns: () => fetchJson(`${API_BASE}/runs`),
  getRun: (runId) => fetchJson(`${API_BASE}/runs/${encodeURIComponent(runId)}`),
  createRun: (payload) =>
    fetchJson(`${API_BASE}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  // destructive (安全装置：confirm=DELETE を必須にしてる前提)
  deleteRun: (runId) =>
    fetchJson(`${API_BASE}/runs/${encodeURIComponent(runId)}${qs({ confirm: "DELETE" })}`, {
      method: "DELETE",
    }),

  cleanupRuns: ({ older_than_days, dry_run }) => {
    const q = { older_than_days, dry_run };
    // dry_run=false のときだけ confirm を付ける運用にしてるならここで付与
    if (!dry_run) q.confirm = "DELETE";
    return fetchJson(`${API_BASE}/runs${qs(q)}`, { method: "DELETE" });
  },

  // Ask / Drill
  ask: (payload) =>
    fetchJson(`${API_BASE}/chat/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getChunk: (chunkId, runId = null) =>
    fetchJson(`${API_BASE}/chunks/${encodeURIComponent(chunkId)}${qs({ run_id: runId })}`),

  getDocPageChunks: (documentId, page, runId = null) =>
    fetchJson(
      `${API_BASE}/docs/${encodeURIComponent(documentId)}/pages/${encodeURIComponent(page)}${qs({
        run_id: runId,
      })}`
    ),
};
