"use client";

import Link from "next/link";
export default function AppNav() {
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
          color: "#0a7",
          fontWeight: 600,
        }}
      >
        Auth: server managed
      </div>
    </nav>
  );
}
