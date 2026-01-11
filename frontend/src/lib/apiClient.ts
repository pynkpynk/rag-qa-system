import { getToken } from "./authToken";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

function normalizeBase(base: string): string {
  let value = (base || API_BASE).trim();
  if (!value) {
    value = API_BASE;
  }
  while (value.endsWith("/")) {
    value = value.slice(0, -1);
  }
  const lower = value.toLowerCase();
  if (lower.endsWith("/api")) {
    value = value.slice(0, -4) || "/";
  }
  return value || "/";
}

function buildApiUrl(base: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const origin = normalizeBase(base);
  const trimmedPath = path.startsWith("/") ? path : `/${path}`;
  if (trimmedPath === "/api" || trimmedPath.startsWith("/api/")) {
    return `${origin}${trimmedPath}`;
  }
  return `${origin}/api${trimmedPath}`;
}

export async function authFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = getToken() || undefined;
  return apiFetch(API_BASE, path, token, undefined, init);
}

export async function apiFetch(
  baseUrl: string,
  path: string,
  token?: string,
  devSub?: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (devSub && !headers.has("x-dev-sub")) {
    headers.set("x-dev-sub", devSub);
  }
  const target = buildApiUrl(baseUrl || API_BASE, path);
  return fetch(target, { ...init, headers });
}
