import { NextResponse } from "next/server";
import { auth0, isAuthConfigured } from "@/lib/auth0";

const handler = auth0.handleAuth();

function notConfiguredResponse() {
  return new NextResponse(null, { status: 404 });
}

type RouteContext = {
  params?: Record<string, string> | undefined;
};

export const GET = (req: Request, ctx: RouteContext) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  return handler(req, ctx);
};

export const POST = (req: Request, ctx: RouteContext) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  return handler(req, ctx);
};
