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
  // auth / demo headers must pass through
  "authorization",
  "x-demo-sub",
  "x-demo-permissions",
  // keep existing (used in local/dev flows)
  "x-dev-sub",
];

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "transfer-encoding",
  "content-length",
  "content-encoding",
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

  // Optional: inject demo token if not provided by caller
  const token = process.env.RAGQA_DEMO_TOKEN;
  const hasAuth = Boolean(headers.get("authorization")?.trim());
  if (token && !hasAuth) {
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
      { status: 500, headers: { "Content-Type": "application/json" } },
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
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }

  const responseHeaders = filterResponseHeaders(upstreamResponse.headers);
  const upstreamContentType = upstreamResponse.headers.get("content-type");
  const jsonish = isJsonLike(upstreamContentType);

  // Stop-the-bleed: always fully buffer to avoid “first chunk only” truncation on Vercel.
  const buf = await upstreamResponse.arrayBuffer();

  let body: BodyInit | null = null;
  if (jsonish) {
    body = decoder.decode(buf);
    // Ensure JSON content-type if upstream omitted/mangled
    if (!responseHeaders.has("content-type")) {
      responseHeaders.set("content-type", "application/json; charset=utf-8");
    }
  } else {
    body = buf;
  }

  return new Response(body, {
    status: upstreamResponse.status,
    headers: responseHeaders,
  });
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
