import { authFetch } from "./apiClient";

export type RunListItem = {
  run_id: string;
  created_at: string;
  status: string;
  document_ids: string[];
};

export type RunDetail = {
  run_id: string;
  created_at: string;
  status: string;
  error?: string | null;
  config: Record<string, unknown>;
  document_ids: string[];
};

async function parseJson<T>(resp: Response): Promise<T> {
  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new Error(`Failed to parse response JSON: ${err}`);
  }
}

export async function listRuns(): Promise<RunListItem[]> {
  const resp = await authFetch("/runs");
  return parseJson<RunListItem[]>(resp);
}

export async function createRun(
  config: Record<string, unknown>,
  documentIds?: string[],
): Promise<RunDetail> {
  const resp = await authFetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      config,
      document_ids: documentIds && documentIds.length > 0 ? documentIds : undefined,
    }),
  });
  return parseJson<RunDetail>(resp);
}

export async function getRun(runId: string): Promise<RunDetail> {
  const resp = await authFetch(`/runs/${runId}`);
  return parseJson<RunDetail>(resp);
}

export async function attachDocsToRun(
  runId: string,
  documentIds: string[],
): Promise<RunDetail> {
  const resp = await authFetch(`/runs/${runId}/attach_docs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_ids: documentIds }),
  });
  return parseJson<RunDetail>(resp);
}

export async function deleteRun(runId: string): Promise<void> {
  const resp = await authFetch(`/runs/${runId}?confirm=DELETE`, {
    method: "DELETE",
  });
  const text = await resp.text();
  if (!resp.ok) {
    const message = text || resp.statusText;
    if (resp.status === 404 || resp.status === 405) {
      throw new Error(`Run delete unsupported: HTTP ${resp.status} ${message}`);
    }
    throw new Error(`HTTP ${resp.status}: ${message}`);
  }
}
