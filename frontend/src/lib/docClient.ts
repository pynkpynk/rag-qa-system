import { authFetch } from "./apiClient";

export async function deleteDoc(documentId: string): Promise<void> {
  const resp = await authFetch(`/docs/${documentId}`, { method: "DELETE" });
  const body = await resp.text();
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
  }
}
