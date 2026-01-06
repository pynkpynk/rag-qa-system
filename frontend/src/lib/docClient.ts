import { authFetch } from "./apiClient";
import { ApiError, apiErrorFromResponse, simpleErrorInfo } from "./errors";

export type DocumentListItem = {
  document_id: string;
  filename: string;
  status: string;
  error?: string | null;
};

export type DocumentUploadResponse = {
  document_id: string;
  filename: string;
  status: string;
  dedup: boolean;
};

async function parseJson<T>(resp: Response): Promise<T> {
  const text = await resp.text();
  if (!resp.ok) {
    throw apiErrorFromResponse(resp, text);
  }
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new ApiError(
      simpleErrorInfo("Invalid JSON response", String(err instanceof Error ? err.message : err)),
    );
  }
}

export async function listDocs(): Promise<DocumentListItem[]> {
  const resp = await authFetch("/docs");
  return parseJson<DocumentListItem[]>(resp);
}

export async function uploadDoc(file: File): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const resp = await authFetch("/docs/upload", {
    method: "POST",
    body: form,
  });
  const text = await resp.text();
  if (!resp.ok) {
    throw apiErrorFromResponse(resp, text);
  }
  try {
    return JSON.parse(text) as DocumentUploadResponse;
  } catch (err) {
    throw new ApiError(
      simpleErrorInfo("Invalid JSON response", String(err instanceof Error ? err.message : err)),
    );
  }
}

export async function deleteDoc(documentId: string): Promise<void> {
  const resp = await authFetch(`/docs/${documentId}`, { method: "DELETE" });
  const body = await resp.text();
  if (!resp.ok) {
    throw apiErrorFromResponse(resp, body);
  }
}
