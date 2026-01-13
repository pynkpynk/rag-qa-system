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
  "x-dev-sub",
];

const RESPONSE_HEADER_ALLOWLIST = [
  "content-type",
  "content-disposition",
  "content-length",
  "etag",
  "cache-control",
  "accept-ranges",
  "last-modified",
  "vary",
];

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
    if (value) {
      headers.set(name, value);
    }
  }
  const token = process.env.RAGQA_DEMO_TOKEN;
  if (token && !headers.has("authorization")) {
    headers.set("authorization", `Bearer ${token}`);
  }
  return headers;
}

function filterResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  for (const name of RESPONSE_HEADER_ALLOWLIST) {
    const value = upstream.get(name);
    if (value) {
      headers.set(name, value);
    }
  }
  return headers;
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
    const body = await request.arrayBuffer();
    init.body = body;
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

  const buffer = await upstreamResponse.arrayBuffer();
  const responseHeaders = filterResponseHeaders(upstreamResponse.headers);
  if (!responseHeaders.has("content-type")) {
    responseHeaders.set("content-type", "application/octet-stream");
  }

  return new Response(buffer, {
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
