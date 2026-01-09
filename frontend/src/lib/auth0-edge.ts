import { initAuth0 as initAuth0Edge } from "@auth0/nextjs-auth0/edge";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { auth0Config } from "./auth0-config";

const auth0EdgeInstance = initAuth0Edge(auth0Config);

export async function runAuthMiddleware(request: NextRequest) {
  const response = NextResponse.next();
  await auth0EdgeInstance.getSession(request, response);
  return response;
}

export const auth0Edge = auth0EdgeInstance;
