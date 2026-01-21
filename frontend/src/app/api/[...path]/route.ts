export const runtime = "nodejs";
export const dynamic = "force-dynamic";

import type { NextRequest } from "next/server";

type HandlerContext = {
  params: { path?: string[] };
};

const REQUEST_HEADER_ALLOWLIST = [
  "content-type",
  "accept",
  "accept-language",
  "range",
  "if-none-match",
  "if-match",
  "if-modified-since",
  "if-unmodified-since",
  "cache-control",
  "pragma",
  // auth / demo / dev headers
  "authorization",
  "x-demo-sub",
  "x-demo-permissions",
  "x-dev-sub",
];

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "transfer-encoding",
  "content-length",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "upgrade",
]);

const decoder = new TextDecoder("utf-8");

function getBackendBase(): string {
  return (process.env.RAGQA_BACKEND_BASE_URL || "").replace(/\/+$/, "");
}

function isLocalBackend(baseUrl: string): boolean {
  if (!baseUrl) return false;
  try {
    const parsed = new URL(baseUrl);
    const host = (parsed.hostname || "").toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host === "::1";
  } catch {
    return false;
  }
}

function buildUpstreamUrl(path: string[], search: string): string {
  const backend = getBackendBase();
  if (!backend) {
    throw new Error("RAGQA_BACKEND_BASE_URL is not configured");
  }
  const suffix = path.length ? `/${path.map(encodeURIComponent).join("/")}` : "";
  return `${backend}/api${suffix}${search}`;
}

function sanitizeUpstreamUrl(value: string): string {
  try {
    const url = new URL(value);
    url.username = "";
    url.password = "";
    url.search = "";
    return url.toString();
  } catch {
    return value.split("?")[0] || value;
  }
}

function buildDevSubCookie(value: string): string {
  const encoded = encodeURIComponent(value);
  return `ragqa_dev_sub=${encoded}; Path=/; SameSite=Lax; HttpOnly`;
}

function decodeDevSub(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function getEffectiveDevSub(request: NextRequest, headers: Headers): string {
  const headerValue = (headers.get("x-dev-sub") || request.headers.get("x-dev-sub") || "").trim();
  if (headerValue) {
    return headerValue;
  }
  const authHeader = (headers.get("authorization") || request.headers.get("authorization") || "").trim();
  if (authHeader) {
    return "";
  }
  const backendBase = getBackendBase();
  const nodeEnv = (process.env.NODE_ENV || "").toLowerCase();
  const cookieAllowed =
    process.env.RAGQA_ALLOW_DEV_SUB_COOKIE === "1" &&
    nodeEnv !== "production" &&
    isLocalBackend(backendBase);
  if (!cookieAllowed) {
    return "";
  }
  const cookieValue = request.cookies.get("ragqa_dev_sub")?.value?.trim() || "";
  if (!cookieValue) {
    return "";
  }
  return decodeDevSub(cookieValue);
}

function encodeRFC5987Value(value: string): string {
  return encodeURIComponent(value).replace(/[!'()*]/g, (char) =>
    `%${char.charCodeAt(0).toString(16).toUpperCase()}`,
  );
}

function extractFilenameFromContentDisposition(value: string): string | null {
  const parts = value.split(";").map((part) => part.trim());
  for (const part of parts) {
    const lower = part.toLowerCase();
    if (lower.startsWith("filename*=")) {
      let raw = part.slice("filename*=".length).trim();
      if (raw.startsWith("UTF-8''") || raw.startsWith("utf-8''")) {
        raw = raw.slice("UTF-8''".length);
      } else if (raw.includes("''")) {
        raw = raw.slice(raw.indexOf("''") + 2);
      }
      try {
        return decodeURIComponent(raw);
      } catch {
        return raw;
      }
    }
  }
  for (const part of parts) {
    const lower = part.toLowerCase();
    if (lower.startsWith("filename=")) {
      let raw = part.slice("filename=".length).trim();
      if (raw.startsWith('"') && raw.endsWith('"') && raw.length >= 2) {
        raw = raw.slice(1, -1);
      }
      return raw;
    }
  }
  return null;
}

function buildSafeContentDisposition(filename: string): string {
  const name = filename || "document.pdf";
  const encoded = encodeRFC5987Value(name);
  return `inline; filename="document.pdf"; filename*=UTF-8''${encoded}`.replace(
    /[\r\n]/g,
    "",
  );
}

function collectRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();

  for (const name of REQUEST_HEADER_ALLOWLIST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  if (!headers.has("accept-encoding")) {
    headers.set("accept-encoding", "identity");
  }

  const effectiveDevSub = getEffectiveDevSub(request, headers);
  if (effectiveDevSub && !headers.get("x-dev-sub")) {
    headers.set("x-dev-sub", effectiveDevSub);
  }

  let auth = (headers.get("authorization") || "").trim();
  if (!auth) {
    const backendBase = getBackendBase();
    const devSub = (headers.get("x-dev-sub") || "").trim();
    const nodeEnv = (process.env.NODE_ENV || "").toLowerCase();
    const allowDevInjection =
      isLocalBackend(backendBase) && (devSub || nodeEnv !== "production");
    if (allowDevInjection) {
      const devToken = process.env.RAGQA_DEV_TOKEN || "dev-token";
      headers.set("authorization", `Bearer ${devToken}`);
      auth = devToken;
    }
  }

  // Optional: inject demo token if caller didn't provide Authorization.
  const token = process.env.RAGQA_DEMO_TOKEN;
  if (token && !auth) {
    headers.set("authorization", `Bearer ${token}`);
  }

  return headers;
}

function filterResponseHeaders(
  upstream: Headers,
  opts?: { addContentTypeFallback?: boolean; stripContentDisposition?: boolean },
): Headers {
  const headers = new Headers();
  const stripContentDisposition = Boolean(opts?.stripContentDisposition);
  upstream.forEach((value, name) => {
    const normalized = name.toLowerCase();
    if (stripContentDisposition && normalized === "content-disposition") {
      return;
    }
    if (!HOP_BY_HOP_HEADERS.has(normalized)) {
      headers.set(name, value);
    }
  });
  const addFallback =
    opts && "addContentTypeFallback" in opts
      ? Boolean(opts.addContentTypeFallback)
      : true;
  if (addFallback && !headers.has("content-type")) {
    headers.set("content-type", "application/octet-stream");
  }
  headers.delete("content-encoding");
  headers.delete("content-length");
  headers.delete("transfer-encoding");
  return headers;
}

function isJsonLike(contentType: string | null): boolean {
  if (!contentType) return false;
  const ct = contentType.toLowerCase();
  return ct.includes("application/json") || ct.includes("+json");
}

async function handleProxy(
  request: NextRequest,
  context: HandlerContext,
): Promise<Response> {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204 });
  }

  const requestPath = context.params.path ?? [];
  if (requestPath.length === 1 && requestPath[0] === "dev-sub") {
    if (request.method.toUpperCase() !== "POST") {
      return new Response(null, { status: 405 });
    }
    let payload: { dev_sub?: string } | null = null;
    try {
      payload = await request.json();
    } catch {
      payload = null;
    }
    const raw = (payload?.dev_sub || "").trim();
    if (!raw) {
      return new Response(JSON.stringify({ ok: false, error: "dev_sub is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      });
    }
    const isProd = (process.env.NODE_ENV || "").toLowerCase() === "production";
    const cookie = `ragqa_dev_sub=${encodeURIComponent(raw)}; Path=/; SameSite=Lax; HttpOnly${
      isProd ? "; Secure" : ""
    }`;
    return new Response(JSON.stringify({ ok: true, dev_sub: raw }), {
      status: 200,
      headers: { "Content-Type": "application/json; charset=utf-8", "Set-Cookie": cookie },
    });
  }

  let upstreamUrl: string;
  try {
    upstreamUrl = buildUpstreamUrl(context.params.path ?? [], request.nextUrl.search || "");
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: {
          code: "BACKEND_NOT_CONFIGURED",
          message: (err as Error).message,
        },
      }),
      { status: 500, headers: { "Content-Type": "application/json; charset=utf-8" } },
    );
  }

  const headers = collectRequestHeaders(request);
  const effectiveDevSub = getEffectiveDevSub(request, headers);
  const isContentRequest =
    requestPath.length >= 3 &&
    requestPath[0] === "docs" &&
    requestPath[2] === "content";

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "follow",
  };

  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    init.body = await request.arrayBuffer();
  }

  const timeoutMs = Number(process.env.RAGQA_UPSTREAM_TIMEOUT_MS || "120000");
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  init.signal = controller.signal;

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl, init);
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return new Response(
        JSON.stringify({
          error: {
            code: "UPSTREAM_TIMEOUT",
            message: `Upstream request timed out after ${timeoutMs}ms.`,
            upstream_url: sanitizeUpstreamUrl(upstreamUrl),
          },
        }),
        {
          status: 504,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "x-ragqa-proxy-timeout": "1",
          },
        },
      );
    }
    return new Response(
      JSON.stringify({
        error: {
          code: "UPSTREAM_FETCH_FAILED",
          message: (err as Error).message,
        },
      }),
      { status: 502, headers: { "Content-Type": "application/json; charset=utf-8" } },
    );
  } finally {
    clearTimeout(timeoutId);
  }

  const isNoContent =
    upstreamResponse.status === 204 || upstreamResponse.status === 205;
  const upstreamContentDisposition = isContentRequest
    ? upstreamResponse.headers.get("content-disposition") || ""
    : "";
  const responseHeaders = filterResponseHeaders(upstreamResponse.headers, {
    addContentTypeFallback: !isNoContent,
    stripContentDisposition: isContentRequest,
  });
  if (isContentRequest && upstreamResponse.ok) {
    const upstreamFilename = upstreamContentDisposition
      ? extractFilenameFromContentDisposition(upstreamContentDisposition)
      : null;
    responseHeaders.set(
      "content-disposition",
      buildSafeContentDisposition(upstreamFilename || "document.pdf"),
    );
  }
  const nodeEnv = (process.env.NODE_ENV || "").toLowerCase();
  const cookieAllowed =
    process.env.RAGQA_ALLOW_DEV_SUB_COOKIE === "1" && nodeEnv !== "production";
  const existingCookieRaw = request.cookies.get("ragqa_dev_sub")?.value?.trim() || "";
  const existingCookie = existingCookieRaw ? decodeDevSub(existingCookieRaw) : "";
  const shouldSetCookie =
    cookieAllowed &&
    upstreamResponse.ok &&
    effectiveDevSub &&
    effectiveDevSub !== existingCookie;
  if (shouldSetCookie) {
    responseHeaders.append("set-cookie", buildDevSubCookie(effectiveDevSub));
  }

  // Debug markers (remove later if you want)
  responseHeaders.set("x-ragqa-proxy", "1");

  if (request.method.toUpperCase() === "HEAD") {
    return new Response(null, { status: upstreamResponse.status, headers: responseHeaders });
  }

  if (isNoContent) {
    return new Response(null, { status: upstreamResponse.status, headers: responseHeaders });
  }

  // Stop-the-bleed: always fully buffer so Vercel/edge streaming quirks can't truncate mid-field.
  const buf = await upstreamResponse.arrayBuffer();
  responseHeaders.set("x-ragqa-proxy-upstream-bytes", String(buf.byteLength));

  const contentType = upstreamResponse.headers.get("content-type");
  const jsonish = isJsonLike(contentType);

  if (jsonish && upstreamResponse.ok) {
    const textBody = decoder.decode(buf);

    // If upstream returns broken JSON, never pass broken JSON to clients.
    try {
      JSON.parse(textBody);
    } catch {
      return new Response(
        JSON.stringify({
          error: {
            code: "UPSTREAM_INVALID_JSON",
            message: "Upstream returned invalid JSON (possibly truncated).",
            upstream_status: upstreamResponse.status,
            upstream_bytes: buf.byteLength,
          },
        }),
        { status: 502, headers: { "Content-Type": "application/json; charset=utf-8" } },
      );
    }

    if (!responseHeaders.get("content-type")?.toLowerCase().includes("json")) {
      responseHeaders.set("content-type", "application/json; charset=utf-8");
    }

    return new Response(textBody, { status: upstreamResponse.status, headers: responseHeaders });
  }

  return new Response(buf, { status: upstreamResponse.status, headers: responseHeaders });
}

export function GET(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
export function POST(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
export function PUT(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
export function PATCH(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
export function DELETE(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
export function HEAD(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
export function OPTIONS(request: NextRequest, context: HandlerContext) {
  return handleProxy(request, context);
}
