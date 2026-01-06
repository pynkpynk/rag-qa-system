export type ErrorInfo = {
  title: string;
  details?: string;
  hint?: string;
};

export class ApiError extends Error {
  info: ErrorInfo;

  constructor(info: ErrorInfo) {
    super(info.details ? `${info.title}: ${info.details}` : info.title);
    this.name = "ApiError";
    this.info = info;
  }
}

function parseBackendErrorPayload(bodyText: string): {
  code?: string;
  message?: string;
} | null {
  if (!bodyText) {
    return null;
  }
  try {
    const parsed = JSON.parse(bodyText);
    if (parsed && typeof parsed === "object" && "error" in parsed) {
      const err = (parsed as { error?: unknown }).error;
      if (err && typeof err === "object") {
        const { code, message } = err as { code?: unknown; message?: unknown };
        return {
          code: typeof code === "string" ? code : undefined,
          message: typeof message === "string" ? message : undefined,
        };
      }
    }
  } catch {
    // fall through to return null
  }
  return null;
}

function classifyStatus(status: number): { title: string; hint?: string } {
  if (status === 401) {
    return { title: "Unauthorized (401)", hint: "Check that the plaintext token is set." };
  }
  if (status === 413) {
    return {
      title: "Payload Too Large (413)",
      hint: "Reduce the PDF size or number of documents in the request.",
    };
  }
  if (status === 422) {
    return {
      title: "Validation Error (422)",
      hint: "Double-check the request payload.",
    };
  }
  return { title: `HTTP ${status}` };
}

export function apiErrorFromResponse(resp: Response, bodyText: string): ApiError {
  const { title, hint } = classifyStatus(resp.status);
  const backend = parseBackendErrorPayload(bodyText);
  let details: string | undefined;
  if (backend) {
    if (backend.code && backend.message) {
      details = `${backend.code}: ${backend.message}`;
    } else if (backend.code || backend.message) {
      details = backend.code || backend.message;
    }
  }
  if (!details) {
    details = bodyText || resp.statusText || "Request failed";
  }
  return new ApiError({
    title,
    details,
    hint,
  });
}

export function simpleErrorInfo(title: string, details?: string): ErrorInfo {
  return { title, details };
}

export function toErrorInfo(err: unknown, fallbackTitle: string): ErrorInfo {
  if (err instanceof ApiError) {
    return err.info;
  }
  if (err instanceof Error) {
    return { title: fallbackTitle, details: err.message };
  }
  return { title: fallbackTitle, details: String(err) };
}
