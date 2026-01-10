import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { auth0Edge } from "@/lib/auth0-edge";

const BUILD_PATHS = [
  "/admin/:path*",
  "/chat/:path*",
  "/runs/:path*",
  "/dev/:path*",
];

const MW_HEADER_NAME = "x-ragqa-mw";
type MiddlewareAction = "next" | "redirect" | "rewrite";

function createMarker(pathname: string) {
  return (response: NextResponse, action: MiddlewareAction) => {
    response.headers.set(MW_HEADER_NAME, `v=1 action=${action} path=${pathname}`);
    return response;
  };
}

function sanitizeReturnTo(value: string, fallback: string): string {
  if (!value) {
    return fallback;
  }
  if (!value.startsWith("/")) {
    return fallback;
  }
  if (value.startsWith("//")) {
    return fallback;
  }
  if (value.includes("://")) {
    return fallback;
  }
  return value;
}

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname || "";
  const mark = createMarker(pathname);
  const inProduction = process.env.NODE_ENV === "production";
  const allowDevRoutes = process.env.ALLOW_DEV_ROUTES === "1";
  const authConfigured = Boolean(
    process.env.AUTH0_BASE_URL &&
      (process.env.AUTH0_ISSUER_BASE_URL || process.env.AUTH0_DOMAIN) &&
      process.env.AUTH0_CLIENT_ID &&
      process.env.AUTH0_CLIENT_SECRET &&
      process.env.AUTH0_SECRET,
  );

  const rewriteTo404 = () => {
    const url = request.nextUrl.clone();
    url.pathname = "/404";
    return mark(NextResponse.rewrite(url), "rewrite");
  };

  const isAdminDevRoute =
    pathname === "/admin/dev" || pathname.startsWith("/admin/dev/");
  const isDevRoute = pathname === "/dev" || pathname.startsWith("/dev/");

  if (isAdminDevRoute) {
    if (inProduction && !allowDevRoutes) {
      return rewriteTo404();
    }
    const url = request.nextUrl.clone();
    url.pathname = "/dev";
    return mark(NextResponse.rewrite(url), "rewrite");
  }

  if (isDevRoute) {
    if (inProduction && !allowDevRoutes) {
      return rewriteTo404();
    }
    if (inProduction) {
      if (!authConfigured) {
        return rewriteTo404();
      }
      const response = mark(NextResponse.next(), "next");
      const session = await auth0Edge().getSession(request, response);
      if (!session) {
        const targetPath = `${pathname}${request.nextUrl.search || ""}` || "/dev";
        const returnTo = sanitizeReturnTo(targetPath, "/dev");
        const loginUrl = request.nextUrl.clone();
        loginUrl.pathname = "/auth/login";
        loginUrl.search = `returnTo=${encodeURIComponent(returnTo)}`;
        return mark(NextResponse.redirect(loginUrl), "redirect");
      }
      return response;
    }
    return mark(NextResponse.next(), "next");
  }

  const requiresAppLogin =
    pathname.startsWith("/chat") || pathname.startsWith("/runs");

  if (requiresAppLogin) {
    if (!authConfigured) {
      return mark(NextResponse.next(), "next");
    }
    const response = mark(NextResponse.next(), "next");
    const session = await auth0Edge().getSession(request, response);
    if (!session) {
      const targetPath = `${pathname}${request.nextUrl.search || ""}`;
      const fallback =
        pathname.startsWith("/runs") || targetPath.startsWith("/runs")
          ? "/runs"
          : "/chat";
      const returnTo = sanitizeReturnTo(targetPath, fallback);
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = "/auth/login";
      loginUrl.search = `returnTo=${encodeURIComponent(returnTo)}`;
      return mark(NextResponse.redirect(loginUrl), "redirect");
    }
    return response;
  }

  if (pathname.startsWith("/admin")) {
    if (!authConfigured) {
      return rewriteTo404();
    }
    return mark(NextResponse.next(), "next");
  }

  return mark(NextResponse.next(), "next");
}

export const config = {
  matcher: BUILD_PATHS,
};
