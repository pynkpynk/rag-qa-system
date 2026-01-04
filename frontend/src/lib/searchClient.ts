import { authFetch } from "./apiClient";

export type SearchHit = {
  chunk_id: string;
  document_id: string;
  page?: number | null;
  chunk_index: number;
  text: string;
  score: number;
  vec_distance?: number | null;
};

type SearchResponse = {
  hits: SearchHit[];
};

export type SearchMode = "selected_docs" | "library";

export async function searchChunks(options: {
  query: string;
  mode: SearchMode;
  documentIds?: string[];
  limit?: number;
}): Promise<SearchResponse> {
  const payload: Record<string, unknown> = {
    q: options.query,
    mode: options.mode,
  };
  if (options.documentIds && options.documentIds.length > 0) {
    payload.document_ids = options.documentIds;
  }
  if (typeof options.limit === "number") {
    payload.limit = options.limit;
  }
  const resp = await authFetch("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
  }
  return JSON.parse(text) as SearchResponse;
}
