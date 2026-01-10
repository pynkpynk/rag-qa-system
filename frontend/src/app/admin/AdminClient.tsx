"use client";

import { useEffect, useState } from "react";

const TOKEN_KEYS = ["ragqa_token", "ragqa.ui.token"];

function loadInitialToken() {
  if (typeof window === "undefined") {
    return "";
  }
  for (const key of TOKEN_KEYS) {
    const value = window.localStorage.getItem(key);
    if (value) {
      return value;
    }
  }
  return "";
}

function maskToken(value: string) {
  if (!value) {
    return "not set";
  }
  if (value.length <= 6) {
    return `set (${value.length} chars)`;
  }
  return `set (${value.length} chars, ${value.slice(0, 3)}…${value.slice(-2)})`;
}

export default function AdminClient() {
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    setToken(loadInitialToken());
  }, []);

  const handleSave = () => {
    if (typeof window === "undefined") {
      return;
    }
    for (const key of TOKEN_KEYS) {
      window.localStorage.setItem(key, token);
    }
    setStatus("Token saved locally.");
  };

  const handleClear = () => {
    if (typeof window === "undefined") {
      return;
    }
    for (const key of TOKEN_KEYS) {
      window.localStorage.removeItem(key);
    }
    setToken("");
    setStatus("Token cleared.");
  };

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
      <h2 style={{ marginBottom: "0.5rem" }}>Bearer Token</h2>
      <p style={{ marginBottom: "0.75rem", color: "#cbd5f5" }}>
        Stored locally under <code>ragqa_token</code> and{" "}
        <code>ragqa.ui.token</code>.
      </p>
      <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
        Token value
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="paste token"
          style={{
            padding: "0.5rem",
            borderRadius: "4px",
            border: "1px solid #475569",
            background: "#0f172a",
            color: "#f8fafc",
          }}
        />
      </label>
      <p style={{ marginTop: "0.5rem", color: "#94a3b8" }}>
        Current status: {maskToken(token)}
      </p>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
        <button
          type="button"
          onClick={handleSave}
          style={{
            padding: "0.4rem 0.8rem",
            borderRadius: "4px",
            background: "#1d4ed8",
            color: "#fff",
            border: "none",
            cursor: "pointer",
          }}
        >
          Save
        </button>
        <button
          type="button"
          onClick={handleClear}
          style={{
            padding: "0.4rem 0.8rem",
            borderRadius: "4px",
            background: "transparent",
            color: "#f87171",
            border: "1px solid #f87171",
            cursor: "pointer",
          }}
        >
          Clear
        </button>
      </div>
      {status && (
        <p style={{ marginTop: "0.5rem", color: "#22c55e" }}>{status}</p>
      )}
    </section>
  );
}
