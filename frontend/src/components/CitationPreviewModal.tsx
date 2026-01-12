"use client";

import { useEffect, useRef, useState } from "react";
import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import { apiFetch } from "../lib/apiClient";
import { DEFAULT_API_BASE } from "../lib/workspace";

GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

type PreviewTarget = {
  documentId: string;
  page: number | null;
};

type CitationPreviewModalProps = {
  open: boolean;
  onClose: () => void;
  target: PreviewTarget | null;
  token?: string | null;
  devSub?: string;
  title?: string;
};

export default function CitationPreviewModal({
  open,
  onClose,
  target,
  token,
  devSub,
  title,
}: CitationPreviewModalProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pageRendered, setPageRendered] = useState<number | null>(null);

  useEffect(() => {
    if (!open) {
      setError(null);
      setPageRendered(null);
    }
  }, [open]);

  useEffect(() => {
    let cancelled = false;
    async function loadPdf() {
      if (!open || !target) {
        return;
      }
      if (!token) {
        setError("Provide a demo token to preview evidence.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const resp = await apiFetch(
          DEFAULT_API_BASE,
          `/docs/${target.documentId}/view`,
          token || undefined,
          devSub || undefined,
        );
        if (!resp.ok) {
          const message = (await resp.text()) || resp.statusText;
          throw new Error(message || "Unable to load evidence.");
        }
        const buffer = await resp.arrayBuffer();
        const pdf = await getDocument({ data: buffer }).promise;
        if (cancelled) return;
        const safePage = target.page && target.page >= 1
          ? Math.min(target.page, pdf.numPages)
          : 1;
        const page = await pdf.getPage(safePage);
        if (cancelled) return;
        const viewport = page.getViewport({ scale: 1.25 });
        const canvas = canvasRef.current;
        if (!canvas) {
          throw new Error("Unable to render preview.");
        }
        const context = canvas.getContext("2d");
        if (!context) {
          throw new Error("Unable to render preview.");
        }
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        await page.render({ canvasContext: context, viewport }).promise;
        if (!cancelled) {
          setPageRendered(safePage);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message || "Unable to load evidence.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadPdf();
    return () => {
      cancelled = true;
    };
  }, [open, target, token, devSub]);

  if (!open) {
    return null;
  }

  const heading = title || "Evidence preview";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(2,6,23,0.8)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "2rem",
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        style={{
          background: "#0f172a",
          borderRadius: "12px",
          padding: "1.5rem",
          maxWidth: "90vw",
          maxHeight: "90vh",
          overflow: "auto",
          border: "1px solid rgba(148,163,184,0.4)",
          color: "#e2e8f0",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: "1.15rem" }}>{heading}</h2>
            {pageRendered ? (
              <p style={{ margin: "0.25rem 0", color: "#94a3b8", fontSize: "0.85rem" }}>
                Page {pageRendered}
              </p>
            ) : null}
          </div>
          <button
            onClick={onClose}
            style={{
              border: "none",
              background: "transparent",
              color: "#e2e8f0",
              fontSize: "1.4rem",
              cursor: "pointer",
            }}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        {!target ? (
          <p style={{ color: "#f87171" }}>No citation details available.</p>
        ) : !token ? (
          <p style={{ color: "#fbbf24" }}>
            Provide a demo token to preview evidence.
          </p>
        ) : loading ? (
          <p>Loading evidence…</p>
        ) : error ? (
          <p style={{ color: "#f87171" }}>{error}</p>
        ) : (
          <canvas
            ref={canvasRef}
            style={{ width: "100%", height: "auto", borderRadius: "8px" }}
          />
        )}
      </div>
    </div>
  );
}
