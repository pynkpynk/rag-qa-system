import type { AppRouteHandlerFnContext } from "@auth0/nextjs-auth0";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getAuth0, isAuthConfigured } from "@/lib/auth0";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const buildTag = process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? "unknown";

function withBuildHeader(response: Response): Response {
  response.headers.set("x-ragqa-build", `v=1 commit=${buildTag}`);
  return response;
}

function notConfiguredResponse() {
  return withBuildHeader(new NextResponse(null, { status: 404 }));
}

function sanitizeReturnTo(value: string | null): string {
  if (!value) {
    return "/chat";
  }
  if (!value.startsWith("/")) {
    return "/chat";
  }
  if (value.startsWith("//")) {
    return "/chat";
  }
  if (value.includes("://")) {
    return "/chat";
  }
  return value;
}

function buildHandler() {
  const auth0 = getAuth0();
  return auth0.handleAuth({
    async login(req: NextRequest, ctx: AppRouteHandlerFnContext) {
      const url = new URL(req.url);
      const safeReturnTo = sanitizeReturnTo(url.searchParams.get("returnTo"));
      return auth0.handleLogin(req, ctx, { returnTo: safeReturnTo });
    },
  });
}

export const GET = async (req: Request, ctx: AppRouteHandlerFnContext) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  const handler = buildHandler();
  const response = await handler(req, ctx);
  return withBuildHeader(response);
};

export const POST = async (req: Request, ctx: AppRouteHandlerFnContext) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  const handler = buildHandler();
  const response = await handler(req, ctx);
  return withBuildHeader(response);
};
