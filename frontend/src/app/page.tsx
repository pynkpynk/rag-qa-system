import type { ReactElement } from "react";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function HomePage(): ReactElement {
  return (
    <main
      style={{
        margin: "0 auto",
        maxWidth: "720px",
        padding: "4rem 1.5rem",
        textAlign: "center",
      }}
    >
      <p style={{ fontWeight: 600, letterSpacing: "0.08em", color: "#6b7280" }}>
        RAG QA System
      </p>
      <h1 style={{ fontSize: "2.5rem", marginTop: "1rem", fontWeight: 700 }}>
        Search your docs with AI
      </h1>
      <p style={{ marginTop: "1rem", fontSize: "1.125rem", color: "#4b5563" }}>
        Upload documents, ask natural language questions, and collaborate with your
        team in a single workspace.
      </p>
      <div style={{ marginTop: "2rem" }}>
        <Link
          href="/console"
          style={{
            display: "inline-block",
            padding: "0.85rem 1.75rem",
            borderRadius: "0.5rem",
            backgroundColor: "#2563eb",
            color: "#fff",
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          Go to Console
        </Link>
      </div>
    </main>
  );
}
