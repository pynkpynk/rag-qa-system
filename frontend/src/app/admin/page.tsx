export default function AdminPage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0f172a",
        color: "#e2e8f0",
        fontFamily: "system-ui, sans-serif",
        padding: "2rem",
      }}
    >
      <h1 style={{ marginBottom: "1rem" }}>Admin Console</h1>
      <p style={{ maxWidth: "480px", lineHeight: 1.5 }}>
        This area is restricted to authorized administrators. Use the provided
        tools to inspect uploaded content and debug integrations.
      </p>
    </main>
  );
}
