import { initAuth0 as initAuth0Edge } from "@auth0/nextjs-auth0/edge";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { buildAuth0Config, isAuthConfigured } from "./auth0-config";

let edgeInstance: ReturnType<typeof initAuth0Edge> | null = null;

function ensureEdge() {
  if (!edgeInstance) {
    edgeInstance = initAuth0Edge(buildAuth0Config());
  }
  return edgeInstance;
}

export async function runAuthMiddleware(request: NextRequest) {
  if (!isAuthConfigured) {
    return NextResponse.next();
  }
  const response = NextResponse.next();
  await ensureEdge().getSession(request, response);
  return response;
}

export const auth0Edge = ensureEdge;
