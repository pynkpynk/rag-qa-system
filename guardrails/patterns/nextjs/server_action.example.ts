"use server";

/**
 * Prefer Server Actions for UI-coupled mutations (forms, buttons),
 * where you do NOT need a public HTTP API surface.
 */
export async function renameDocumentAction(input: {
  docId: string;
  title: string;
}): Promise<{ ok: true }> {
  // TODO: call backend service or DB layer server-side
  // - keep validation here
  // - throw typed errors (mapped to UiError in UI)
  if (!input.title.trim()) {
    throw new Error("Title is required");
  }
  return { ok: true };
}
