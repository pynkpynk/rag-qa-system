import type { ReactElement } from "react";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function HomePage(): ReactElement {
  const demoEnabled = process.env.DEMO_ENTRY_ENABLED === "1";
  return (
    <main
      style={{
        minHeight: "100dvh",
        padding: "4rem 1.5rem 5rem",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background:
          "radial-gradient(circle at 20% 20%, rgba(34,197,94,0.15), transparent 45%), radial-gradient(circle at 80% 0%, rgba(74,222,128,0.2), transparent 55%)",
        textAlign: "center",
      }}
    >
      <div
        style={{
          maxWidth: "760px",
          width: "100%",
          borderRadius: "18px",
          padding: "3rem 2rem",
          background:
            "linear-gradient(135deg, rgba(15,23,42,0.9), rgba(2,6,23,0.9))",
          border: "1px solid rgba(16,185,129,0.25)",
          boxShadow: "0 30px 60px rgba(2,6,23,0.75)",
        }}
      >
        <p
          className="font-display"
          style={{
            textTransform: "uppercase",
            letterSpacing: "0.25em",
            fontSize: "0.85rem",
            color: "#86efac",
            marginBottom: "1.5rem",
          }}
        >
          Evidence / Audit / Governance
        </p>
        <h1
          style={{
            fontSize: "2.75rem",
            lineHeight: 1.2,
            fontWeight: 700,
            marginBottom: "1.25rem",
          }}
        >
          Evidence-first answers from your documents.
        </h1>
        <p
          style={{
            fontSize: "1.15rem",
            color: "#cbd5f5",
            marginBottom: "2rem",
          }}
        >
          Audit-ready citations, traceable runs, and governance-friendly workflows
          designed for enterprise knowledge teams who need to prove every claim.
        </p>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "1rem",
          }}
        >
          <Link
            href="/console"
            style={{
              padding: "0.95rem 1.9rem",
              borderRadius: "999px",
              background: "linear-gradient(90deg, #10b981, #16a34a)",
              color: "#0b1120",
              fontWeight: 600,
              boxShadow: "0 10px 30px rgba(16,185,129,0.35)",
            }}
          >
            Launch Console
          </Link>
          {demoEnabled ? (
            <Link
              href="/demo"
              style={{
                padding: "0.95rem 1.9rem",
                borderRadius: "999px",
                border: "1px solid rgba(148,163,184,0.5)",
                color: "#e2e8f0",
                fontWeight: 600,
              }}
            >
              Try Demo
            </Link>
          ) : null}
          <a
            href="https://github.com/pynkpynk"
            target="_blank"
            rel="noreferrer"
            style={{
              padding: "0.95rem 1.9rem",
              borderRadius: "999px",
              border: "1px solid rgba(148,163,184,0.5)",
              color: "#e2e8f0",
              fontWeight: 600,
            }}
          >
            View GitHub
          </a>
        </div>
      </div>

      <div
        style={{
          marginTop: "2.5rem",
          maxWidth: "680px",
          color: "#9ca3af",
          fontSize: "0.95rem",
        }}
      >
        <p>
          Every answer is backed by citations and run metadata so audit teams can
          trace how insights were produced. When you are ready, sign in to the
          console to upload evidence, review runs, and collaborate with governed
          AI workflows.
        </p>
      </div>
    </main>
  );
}
