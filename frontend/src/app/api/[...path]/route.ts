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

function buildUpstreamUrl(path: string[], search: string): string {
  const backend = (process.env.RAGQA_BACKEND_BASE_URL || "").replace(/\/+$/, "");
  if (!backend) {
    throw new Error("RAGQA_BACKEND_BASE_URL is not configured");
  }
  const suffix = path.length ? `/${path.map(encodeURIComponent).join("/")}` : "";
  return `${backend}/api${suffix}${search}`;
}

function collectRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();

  for (const name of REQUEST_HEADER_ALLOWLIST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  // Optional: inject demo token if caller didn't provide Authorization.
  const token = process.env.RAGQA_DEMO_TOKEN;
  const auth = headers.get("authorization") || "";
  if (token && !auth.trim()) {
    headers.set("authorization", `Bearer ${token}`);
  }

  return headers;
}

function filterResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  upstream.forEach((value, name) => {
    if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase())) {
      headers.set(name, value);
    }
  });
  if (!headers.has("content-type")) {
    headers.set("content-type", "application/octet-stream");
  }
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

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "follow",
  };

  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    init.body = await request.arrayBuffer();
  }

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl, init);
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: {
          code: "UPSTREAM_FETCH_FAILED",
          message: (err as Error).message,
        },
      }),
      { status: 502, headers: { "Content-Type": "application/json; charset=utf-8" } },
    );
  }

  const responseHeaders = filterResponseHeaders(upstreamResponse.headers);

  // Debug markers (remove later if you want)
  responseHeaders.set("x-ragqa-proxy", "1");

  if (request.method.toUpperCase() === "HEAD") {
    return new Response(null, { status: upstreamResponse.status, headers: responseHeaders });
  }

  // Stop-the-bleed: always fully buffer so Vercel/edge streaming quirks can't truncate mid-field.
  const buf = await upstreamResponse.arrayBuffer();
  responseHeaders.set("x-ragqa-proxy-upstream-bytes", String(buf.byteLength));

  const contentType = upstreamResponse.headers.get("content-type");
  const jsonish = isJsonLike(contentType);

  if (jsonish) {
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
