const STORAGE_KEY = "ragqa_token";

export function getToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const token = window.localStorage.getItem(STORAGE_KEY);
  return token && token.trim().length > 0 ? token : null;
}

export function setToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  if (token.trim().length === 0) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, token.trim());
}

export function clearToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}
