import { HttpError } from "./fetcher";

export type UiError = {
  title: string;
  message: string;
  code?: string;
  status?: number;
};

export function toUiError(err: unknown): UiError {
  // Normalize unknown errors into a safe, user-facing shape.
  if (err instanceof HttpError) {
    const code =
      (err.payload as any)?.error?.code ??
      (err.payload as any)?.error?.error?.code; // defensive
    const message =
      (err.payload as any)?.error?.message ??
      err.message ??
      "Request failed.";
    return {
      title: "Request failed",
      message,
      code,
      status: err.status,
    };
  }

  if (err instanceof Error) {
    return { title: "Something went wrong", message: err.message };
  }

  return { title: "Something went wrong", message: "Unknown error occurred." };
}
