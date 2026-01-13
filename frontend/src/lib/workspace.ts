const DEFAULT_API_BASE = "/api";

export function normalizeApiBase(input?: string): string {
  void input;
  return DEFAULT_API_BASE;
}

export { DEFAULT_API_BASE };
