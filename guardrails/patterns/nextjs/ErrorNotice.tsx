import type { UiError } from "./ui_error";

export function ErrorNotice({ error }: { error: UiError }) {
  return (
    <div role="alert" aria-live="polite">
      <h3>{error.title}</h3>
      <p>{error.message}</p>
      {error.code ? <small>Code: {error.code}</small> : null}
    </div>
  );
}
