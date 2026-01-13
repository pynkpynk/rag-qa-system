const API_BASE = "/api";

function buildApiUrl(base: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const baseValue = base || API_BASE;
  const baseTrimmed = baseValue.endsWith("/")
    ? baseValue.slice(0, -1)
    : baseValue;
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${baseTrimmed}${suffix}`;
}

export async function authFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  return apiFetch(API_BASE, path, undefined, init);
}

export async function apiFetch(
  baseUrl: string,
  path: string,
  devSub?: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (devSub && !headers.has("x-dev-sub")) {
    headers.set("x-dev-sub", devSub);
  }
  const target = buildApiUrl(baseUrl, path);
  return fetch(target, { ...init, headers, cache: init.cache ?? "no-store" });
}
