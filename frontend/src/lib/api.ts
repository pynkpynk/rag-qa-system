export type ApiError = {
  status: number;
  code: string;
  message: string;
  details?: unknown;
  requestId?: string;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

const API_BASE = "/api";

function pickRequestId(res: Response): string | undefined {
  return res.headers.get("x-request-id") ?? undefined;
}

export async function apiFetch<T>(
  path: string,
  opts: {
    method?: string;
    headers?: Record<string, string>;
    body?: BodyInit | null;
    runToken?: string;
  } = {}
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (opts.runToken) headers["X-Run-Token"] = opts.runToken;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body ?? null
    });
  } catch (e) {
    return {
      ok: false,
      error: {
        status: 0,
        code: "NETWORK_ERROR",
        message: "Network error (cannot reach server).",
        details: String(e)
      }
    };
  }

  const requestId = pickRequestId(res);

  // 204などbodyなし
  const text = await res.text();
  const json = text ? safeJsonParse(text) : null;

  if (res.ok) {
    return { ok: true, data: (json ?? ({} as T)) as T };
  }

  // Backendが統一形式で返す前提：{ error: { code, message, details? } }
  const err = (json?.error ?? {}) as { code?: string; message?: string; details?: unknown };
  return {
    ok: false,
    error: {
      status: res.status,
      code: err.code ?? "UNKNOWN_ERROR",
      message: err.message ?? `Request failed (${res.status})`,
      details: err.details,
      requestId
    }
  };
}

function safeJsonParse(s: string): any | null {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}
