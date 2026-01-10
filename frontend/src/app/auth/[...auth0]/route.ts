import type { AppRouteHandlerFnContext } from "@auth0/nextjs-auth0";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getAuth0, isAuthConfigured } from "@/lib/auth0";

function notConfiguredResponse() {
  return new NextResponse(null, { status: 404 });
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

export const GET = (req: Request, ctx: AppRouteHandlerFnContext) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  const handler = buildHandler();
  return handler(req, ctx);
};

export const POST = (req: Request, ctx: AppRouteHandlerFnContext) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  const handler = buildHandler();
  return handler(req, ctx);
};
