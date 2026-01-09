import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

function isAuthConfigured(): boolean {
  return Boolean(
    process.env.AUTH0_SECRET &&
      (process.env.AUTH0_ISSUER_BASE_URL || process.env.AUTH0_DOMAIN) &&
      process.env.AUTH0_CLIENT_ID &&
      process.env.AUTH0_CLIENT_SECRET,
  );
}

export async function middleware(request: NextRequest) {
  if (!isAuthConfigured()) {
    const url = request.nextUrl.clone();
    url.pathname = "/404";
    return NextResponse.rewrite(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/auth/:path*"],
};
