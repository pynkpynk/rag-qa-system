import type { ReactElement } from "react";

export const dynamic = "force-dynamic";

export default function ChatPage(): ReactElement {
  return (
    <main style={{ margin: "0 auto", maxWidth: "960px", padding: "3rem 1rem" }}>
      <h1 style={{ fontSize: "2rem", fontWeight: 600 }}>Chat</h1>
      <p style={{ marginTop: "1rem", fontSize: "1rem" }}>
        Chat workspace will appear here once you are signed in.
      </p>
    </main>
  );
}
