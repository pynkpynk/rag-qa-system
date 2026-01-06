import { ErrorInfo } from "../lib/errors";

type ErrorBannerProps = {
  error: ErrorInfo | null;
};

export default function ErrorBanner({ error }: ErrorBannerProps) {
  if (!error) {
    return null;
  }
  return (
    <div
      style={{
        background: "#fee",
        border: "1px solid #f88",
        color: "#800",
        padding: "0.5rem 0.75rem",
        borderRadius: "4px",
        margin: "0.5rem 0",
        whiteSpace: "pre-wrap",
      }}
    >
      <strong>{error.title}</strong>
      {error.details && <div>{error.details}</div>}
      {error.hint && <div style={{ fontStyle: "italic" }}>{error.hint}</div>}
    </div>
  );
}
