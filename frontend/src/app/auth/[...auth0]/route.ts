import { NextResponse } from "next/server";
import { auth0, isAuthConfigured } from "@/lib/auth0";

const handler = auth0.handleAuth();

function notConfiguredResponse() {
  return new NextResponse(null, { status: 404 });
}

export const GET = (req: Request) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  return handler(req);
};

export const POST = (req: Request) => {
  if (!isAuthConfigured) {
    return notConfiguredResponse();
  }
  return handler(req);
};
