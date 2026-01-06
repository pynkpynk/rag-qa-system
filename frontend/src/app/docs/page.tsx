"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import TokenGate from "../../components/TokenGate";
import ErrorBanner from "../../components/ErrorBanner";
import {
  deleteDoc,
  listDocs,
  uploadDoc,
  type DocumentListItem,
  type DocumentUploadResponse,
} from "../../lib/docClient";
import { getToken } from "../../lib/authToken";
import { ErrorInfo, simpleErrorInfo, toErrorInfo } from "../../lib/errors";

export default function DocsPage() {
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [docsError, setDocsError] = useState<ErrorInfo | null>(null);
  const [docsLoading, setDocsLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ErrorInfo | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<DocumentUploadResponse | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refreshDocs = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setDocs([]);
      setDocsError(simpleErrorInfo("Token required", "Set a demo token to continue."));
      return;
    }
    setDocsLoading(true);
    setDocsError(null);
    try {
      const data = await listDocs();
      setDocs(data);
    } catch (err) {
      setDocs([]);
      setDocsError(toErrorInfo(err, "Failed to load documents"));
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshDocs().catch(() => null);
  }, [refreshDocs]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError(simpleErrorInfo("File required", "Choose a PDF before uploading."));
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const resp = await uploadDoc(selectedFile);
      setUploadSuccess(resp);
      setSelectedFile(null);
      await refreshDocs();
    } catch (err) {
      setUploadSuccess(null);
      setUploadError(toErrorInfo(err, "Upload failed"));
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (documentId: string) => {
    if (!confirm("Delete this document?")) {
      return;
    }
    setDeletingId(documentId);
    try {
      await deleteDoc(documentId);
      await refreshDocs();
    } catch (err) {
      setDocsError(toErrorInfo(err, "Delete failed"));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main style={{ padding: "1rem" }}>
      <h1>Documents</h1>
      <TokenGate>
        <section
          style={{
            margin: "1rem 0",
            padding: "1rem",
            border: "1px solid #ddd",
            borderRadius: "4px",
          }}
        >
          <h2>Upload PDF</h2>
          <form onSubmit={handleUpload}>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => {
                const file = e.target.files?.[0] ?? null;
                setSelectedFile(file);
              }}
              style={{ marginBottom: "0.5rem" }}
            />
            <div>
              <button type="submit" disabled={uploading}>
                {uploading ? "Uploading..." : "Upload PDF"}
              </button>
            </div>
          </form>
          {uploadSuccess && (
            <div style={{ marginTop: "0.5rem", color: "#0a7" }}>
              Uploaded {uploadSuccess.filename} (id {uploadSuccess.document_id})
            </div>
          )}
          <ErrorBanner error={uploadError} />
        </section>

        <section
          style={{
            margin: "1rem 0",
            padding: "1rem",
            border: "1px solid #ddd",
            borderRadius: "4px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <h2>My Documents</h2>
            <button type="button" onClick={() => refreshDocs()} disabled={docsLoading}>
              {docsLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <ErrorBanner error={docsError} />
          {docsLoading && <p>Loading documents...</p>}
          {!docsLoading && docs.length === 0 && (
            <p style={{ color: "#555" }}>No documents found yet.</p>
          )}
          {!docsLoading && docs.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th align="left">Filename</th>
                  <th align="left">Status</th>
                  <th align="left">Document ID</th>
                  <th align="left">Error</th>
                  <th align="left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.document_id}>
                    <td>{doc.filename}</td>
                    <td>{doc.status}</td>
                    <td>
                      <code>{doc.document_id}</code>
                    </td>
                    <td>{doc.error || "-"}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => handleDelete(doc.document_id)}
                        disabled={deletingId === doc.document_id}
                      >
                        {deletingId === doc.document_id ? "Deleting..." : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </TokenGate>
    </main>
  );
}
