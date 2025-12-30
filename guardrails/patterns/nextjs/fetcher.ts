export type ApiError = {
  error: {
    code: string;
    message: string;
    hint?: string | null;
    extra?: Record<string, unknown> | null;
  };
};

export class HttpError extends Error {
  public readonly status: number;
  public readonly payload?: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

export async function apiFetch<T>(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(input, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const text = await res.text();
  const payload = text ? safeJsonParse(text) : undefined;

  if (!res.ok) {
    const msg =
      (payload as ApiError | undefined)?.error?.message ??
      `Request failed with ${res.status}`;
    throw new HttpError(res.status, msg, payload);
  }

  return payload as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}
