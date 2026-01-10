import type { ReactElement } from "react";

export const dynamic = "force-dynamic";

export default function RunsPage(): ReactElement {
  return (
    <main style={{ margin: "0 auto", maxWidth: "960px", padding: "3rem 1rem" }}>
      <h1 style={{ fontSize: "2rem", fontWeight: 600 }}>Runs</h1>
      <p style={{ marginTop: "1rem", fontSize: "1rem" }}>
        Execution history will appear here once authenticated.
      </p>
    </main>
  );
}
