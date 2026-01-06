import { authFetch } from "./apiClient";

export type ChunkDetail = {
  chunk_id: string;
  document_id: string;
  filename?: string | null;
  page?: number | null;
  chunk_index: number;
  text: string;
};

async function parseChunk(resp: Response): Promise<ChunkDetail> {
  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
  }
  try {
    return JSON.parse(text) as ChunkDetail;
  } catch (err) {
    throw new Error(`Failed to parse chunk JSON: ${err}`);
  }
}

export async function getChunk(chunkId: string): Promise<ChunkDetail> {
  const resp = await authFetch(`/chunks/${chunkId}`);
  return parseChunk(resp);
}
