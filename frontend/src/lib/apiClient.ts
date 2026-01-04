import { getToken } from "./authToken";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export async function authFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const target = path.startsWith("http")
    ? path
    : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  return fetch(target, { ...init, headers });
}
