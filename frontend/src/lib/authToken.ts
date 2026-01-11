const CANONICAL_KEY = "ragqa.demo.token";
const LEGACY_KEYS = ["ragqa_token", "ragqa.ui.token"];

export function getToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const readKey = (key: string) => {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    const trimmed = raw.trim();
    return trimmed.length > 0 ? trimmed : null;
  };
  const canonical = readKey(CANONICAL_KEY);
  if (canonical) {
    return canonical;
  }
  for (const key of LEGACY_KEYS) {
    const legacy = readKey(key);
    if (legacy) {
      return legacy;
    }
  }
  return null;
}

export function setToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const trimmed = token.trim();
  if (trimmed.length === 0) {
    clearToken();
    return;
  }
  window.localStorage.setItem(CANONICAL_KEY, trimmed);
  for (const key of LEGACY_KEYS) {
    window.localStorage.removeItem(key);
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(CANONICAL_KEY);
  for (const key of LEGACY_KEYS) {
    window.localStorage.removeItem(key);
  }
}
