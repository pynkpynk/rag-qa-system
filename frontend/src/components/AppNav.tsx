"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken } from "../lib/authToken";

export default function AppNav() {
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    const update = () => setHasToken(Boolean(getToken()));
    update();
    const listener = () => update();
    window.addEventListener("storage", listener);
    window.addEventListener("ragqa-token-change", listener as EventListener);
    return () => {
      window.removeEventListener("storage", listener);
      window.removeEventListener("ragqa-token-change", listener as EventListener);
    };
  }, []);

  return (
    <nav
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "0.75rem 1rem",
        borderBottom: "1px solid #ddd",
        background: "#fafafa",
      }}
    >
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <Link href="/">Console</Link>
      </div>
      <div
        style={{
          fontSize: "0.9rem",
          color: hasToken ? "#0a7" : "#b00",
          fontWeight: 600,
        }}
      >
        Token: {hasToken ? "set" : "missing"}
      </div>
    </nav>
  );
}
