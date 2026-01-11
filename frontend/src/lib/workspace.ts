const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export function normalizeApiBase(input: string): string {
  let value = (input || DEFAULT_API_BASE).trim();
  if (!value) {
    value = DEFAULT_API_BASE;
  }
  while (value.endsWith("/")) {
    value = value.slice(0, -1);
  }
  if (!value.toLowerCase().endsWith("/api")) {
    value = `${value}/api`;
  }
  return value;
}

export function buildAuthHeaders(
  token?: string,
  extra?: Record<string, string | undefined>,
): Headers {
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (extra) {
    for (const [key, val] of Object.entries(extra)) {
      if (val) {
        headers.set(key, val);
      }
    }
  }
  return headers;
}

export { DEFAULT_API_BASE };
