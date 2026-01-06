"use client";

import { useCallback, useEffect, useState } from "react";
import { clearToken, getToken, setToken } from "../lib/authToken";
import ErrorBanner from "./ErrorBanner";
import { ErrorInfo, simpleErrorInfo } from "../lib/errors";

type TokenGateProps = {
  children: React.ReactNode;
};

export default function TokenGate({ children }: TokenGateProps) {
  const [tokenValue, setTokenValue] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const [message, setMessage] = useState<ErrorInfo | null>(null);

  const normalizeToken = (value: string) => {
    let trimmed = value.trim();
    const bearerPrefix = "bearer ";
    if (trimmed.toLowerCase().startsWith(bearerPrefix)) {
      trimmed = trimmed.slice(bearerPrefix.length).trim();
    }
    return trimmed;
  };

  const syncTokenState = useCallback(() => {
    const stored = getToken();
    setTokenValue(stored ?? "");
    setHasToken(Boolean(stored));
  }, []);

  useEffect(() => {
    syncTokenState();
    if (typeof window === "undefined") {
      return;
    }
    const handler = () => syncTokenState();
    window.addEventListener("ragqa-token-change", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("ragqa-token-change", handler);
      window.removeEventListener("storage", handler);
    };
  }, [syncTokenState]);

  const handleSave = () => {
    const cleaned = normalizeToken(tokenValue);
    if (!cleaned) {
      setMessage(simpleErrorInfo("Token required", "Enter the plaintext demo token."));
      return;
    }
    setToken(cleaned);
    setTokenValue(cleaned);
    setHasToken(true);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("ragqa-token-change"));
    }
    setMessage(null);
  };

  const handleClear = () => {
    clearToken();
    setTokenValue("");
    setHasToken(false);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("ragqa-token-change"));
    }
    setMessage(null);
  };

  if (!hasToken) {
    return (
      <section
        style={{
          border: "1px solid #ccc",
          padding: "1rem",
          margin: "1rem 0",
          borderRadius: "4px",
        }}
      >
        <h2>Set Demo Token</h2>
        <p style={{ marginBottom: "0.5rem" }}>
          Paste a valid demo token to access the API.
        </p>
        <input
          type="password"
          value={tokenValue}
          onChange={(e) => setTokenValue(normalizeToken(e.target.value))}
          style={{ width: "100%", padding: "0.4rem", marginBottom: "0.5rem" }}
          placeholder="demo token"
        />
        <p style={{ margin: "0.25rem 0", fontSize: "0.85rem", color: "#555" }}>
          Paste plaintext token (example: demo_token_a). The field accepts only the value,
          not &ldquo;Bearer ...&rdquo;.
        </p>
        <div>
          <button
            type="button"
            onClick={handleSave}
            style={{ marginRight: "0.5rem" }}
          >
            Save Token
          </button>
          <button type="button" onClick={handleClear}>
            Clear Token
          </button>
        </div>
        <ErrorBanner error={message} />
      </section>
    );
  }

  return (
    <>
      <div
        style={{
          margin: "1rem 0",
          padding: "0.5rem 0.75rem",
          border: "1px solid #cde",
          background: "#f8fbff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderRadius: "4px",
        }}
      >
        <span>Token is set. You can clear it anytime.</span>
        <button type="button" onClick={handleClear}>
          Clear Token
        </button>
      </div>
      {children}
    </>
  );
}
