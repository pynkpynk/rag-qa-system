const API_BASE = import.meta.env.VITE_API_BASE || "/api";

/**
 * Small helper to generate a request id for debugging / correlation.
 * - Prefer crypto.randomUUID() if available
 * - Fallback to a timestamp-ish id
 */
function newRequestId() {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // noop
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

async function fetchJson(path, options = {}) {
  const url = `${API_BASE}${path}`;

  // Normalize headers (so we can safely set X-Request-ID / Accept)
  const headers = new Headers(options.headers || {});
  const reqId = headers.get("X-Request-ID") || newRequestId();

  headers.set("X-Request-ID", reqId);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  const res = await fetch(url, { ...options, headers });

  // Server may echo back X-Request-ID (or we use our own)
  const echoedReqId = res.headers.get("x-request-id") || reqId;

  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const ct = res.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const j = await res.json();
        msg = j?.detail || j?.message || JSON.stringify(j);
      } else {
        const t = await res.text();
        msg = t || msg;
      }
    } catch {
      // noop
    }

    // Include request id + endpoint for faster debugging
    throw new Error(`[${echoedReqId}] ${path}: ${msg}`);
  }

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return { raw: await res.text().catch(() => "") };
}

export const api = {
  // Docs
  listDocs() {
    return fetchJson("/docs");
  },
  uploadPdf(file) {
    const fd = new FormData();
    fd.append("file", file);
    return fetchJson("/docs/upload", { method: "POST", body: fd });
  },

  // Runs
  listRuns() {
    return fetchJson("/runs");
  },
  getRun(runId) {
    return fetchJson(`/runs/${encodeURIComponent(runId)}`);
  },
  createRun(payload) {
    return fetchJson("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  deleteRun(runId) {
    // backend is requiring confirm=DELETE
    return fetchJson(`/runs/${encodeURIComponent(runId)}?confirm=DELETE`, {
      method: "DELETE",
    });
  },
  cleanupRuns({ older_than_days, dry_run }) {
    const u = new URLSearchParams();
    u.set("older_than_days", String(older_than_days));
    u.set("dry_run", String(Boolean(dry_run)));
    if (!dry_run) u.set("confirm", "DELETE");
    return fetchJson(`/runs?${u.toString()}`, { method: "DELETE" });
  },
  attachDocs(runId, documentIds) {
    return fetchJson(`/runs/${encodeURIComponent(runId)}/attach_docs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: documentIds }),
    });
  },

  // Ask
  ask(payload) {
    return fetchJson("/chat/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  // Drilldown
  getChunk(chunkId, runId = null) {
    const u = new URLSearchParams();
    if (runId) u.set("run_id", runId);
    const qs = u.toString() ? `?${u.toString()}` : "";
    return fetchJson(`/chunks/${encodeURIComponent(chunkId)}${qs}`);
  },
  getDocPageChunks(documentId, page, runId = null) {
    const u = new URLSearchParams();
    if (runId) u.set("run_id", runId);
    const qs = u.toString() ? `?${u.toString()}` : "";
    return fetchJson(
      `/docs/${encodeURIComponent(documentId)}/pages/${encodeURIComponent(page)}${qs}`
    );
  },
};
