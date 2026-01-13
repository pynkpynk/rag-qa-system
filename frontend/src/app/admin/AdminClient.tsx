"use client";

export default function AdminClient() {
  return (
    <section
      style={{
        border: "1px solid #334155",
        borderRadius: "6px",
        padding: "1rem",
        background: "rgba(15, 23, 42, 0.8)",
        marginTop: "1.5rem",
      }}
    >
      <h2 style={{ marginBottom: "0.5rem" }}>Authentication</h2>
      <p style={{ marginBottom: "0.75rem", color: "#cbd5f5" }}>
        Tokens are handled entirely on the server. No browser storage or manual entry
        is required.
      </p>
      <p style={{ color: "#94a3b8" }}>
        If backend credentials change, update the environment variables on the server
        and redeploy&mdash;the UI will automatically use the new credentials.
      </p>
    </section>
  );
}
