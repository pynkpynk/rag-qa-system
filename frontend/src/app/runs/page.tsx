"use client";

import { useState } from "react";
import TokenGate from "../../components/TokenGate";
import ErrorBanner from "../../components/ErrorBanner";
import { listRuns, type RunListItem } from "../../lib/runClient";
import { ErrorInfo, toErrorInfo } from "../../lib/errors";

export default function RunsPage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runsError, setRunsError] = useState<ErrorInfo | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchRuns = async () => {
    setLoading(true);
    setRunsError(null);
    try {
      const data = await listRuns();
      setRuns(data);
    } catch (err) {
      setRuns([]);
      setRunsError(toErrorInfo(err, "Failed to load runs"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ padding: "1rem" }}>
      <h1>Runs</h1>
      <TokenGate>
        <section
          style={{
            border: "1px solid #ddd",
            padding: "1rem",
            borderRadius: "4px",
          }}
        >
          <button type="button" onClick={() => fetchRuns()} disabled={loading}>
            {loading ? "Loading..." : "Fetch Runs"}
          </button>
          <ErrorBanner error={runsError} />
          {loading && <p>Loading run list...</p>}
          {!loading && runs.length === 0 && (
            <p style={{ color: "#555", marginTop: "1rem" }}>
              No runs loaded. Click &ldquo;Fetch Runs&rdquo; to view your run history.
            </p>
          )}
          {!loading && runs.length > 0 && (
            <ul style={{ marginTop: "1rem" }}>
              {runs.map((run) => (
                <li
                  key={run.run_id}
                  style={{
                    border: "1px solid #eee",
                    padding: "0.75rem",
                    borderRadius: "4px",
                    marginBottom: "0.5rem",
                  }}
                >
                  <div>
                    <strong>{run.run_id}</strong>
                  </div>
                  <div>Status: {run.status}</div>
                  <div>Documents attached: {run.document_ids.length}</div>
                  <div>Created: {run.created_at}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </TokenGate>
    </main>
  );
}
