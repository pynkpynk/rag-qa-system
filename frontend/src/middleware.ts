import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { auth0Edge } from "@/lib/auth0-edge";
import { isAuthConfigured } from "@/lib/auth0-config";

const MW_HEADER_NAME = "x-ragqa-mw";

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
  const inProduction = process.env.NODE_ENV === "production";
  const allowDevRoutes = process.env.ALLOW_DEV_ROUTES === "1";
  const demoEnabled = Boolean((process.env.RAGQA_DEMO_TOKEN || "").trim());
  const authConfigured = isAuthConfigured;
  const authFlag = authConfigured ? "1" : "0";
  const mw = (action: string, response: NextResponse) => {
    response.headers.set(
      MW_HEADER_NAME,
      `v=1 action=${action} path=${pathname} authcfg=${authFlag}`,
    );
    return response;
  };

  const rewriteTo404 = () => {
    const url = request.nextUrl.clone();
    url.pathname = "/404";
    return mw("rewrite:/404", NextResponse.rewrite(url));
  };

  if (pathname === "/_demo" || pathname.startsWith("/_demo/")) {
    return rewriteTo404();
  }

  if (pathname === "/demo") {
    if (!demoEnabled) {
      return rewriteTo404();
    }
    const url = request.nextUrl.clone();
    url.pathname = "/_demo";
    return mw("rewrite:/_demo", NextResponse.rewrite(url));
  }

  if (pathname.startsWith("/demo/")) {
    return rewriteTo404();
  }

  const isAdminDevRoute =
    pathname === "/admin/dev" || pathname.startsWith("/admin/dev/");
  const isDevRoute = pathname === "/dev" || pathname.startsWith("/dev/");

  if (isAdminDevRoute) {
    if (inProduction && !allowDevRoutes) {
      return rewriteTo404();
    }
    const url = request.nextUrl.clone();
    url.pathname = "/dev";
    return mw("rewrite:/dev", NextResponse.rewrite(url));
  }

  if (isDevRoute) {
    if (inProduction && !allowDevRoutes) {
      return rewriteTo404();
    }
    if (inProduction) {
      if (!authConfigured) {
        return rewriteTo404();
      }
      const response = mw("next", NextResponse.next());
      const session = await auth0Edge().getSession(request, response);
      if (!session) {
        const targetPath = `${pathname}${request.nextUrl.search || ""}` || "/dev";
        const returnTo = sanitizeReturnTo(targetPath, "/dev");
        const loginUrl = request.nextUrl.clone();
        loginUrl.pathname = "/auth/login";
        loginUrl.search = `returnTo=${encodeURIComponent(returnTo)}`;
        return mw("redirect:/auth/login", NextResponse.redirect(loginUrl));
      }
      return response;
    }
    return mw("next", NextResponse.next());
  }

  const isChatRoute = pathname === "/chat" || pathname.startsWith("/chat/");
  const isRunsRoute = pathname === "/runs" || pathname.startsWith("/runs/");
  const redirectToConsole = () => {
    const url = request.nextUrl.clone();
    url.pathname = "/console";
    return mw("redirect:/console", NextResponse.redirect(url, 308));
  };

  if (isChatRoute || isRunsRoute) {
    return redirectToConsole();
  }

  const isConsoleRoute =
    pathname === "/console" || pathname.startsWith("/console/");

  if (isConsoleRoute) {
    if (!authConfigured) {
      if (inProduction) {
        return rewriteTo404();
      }
      return mw("next", NextResponse.next());
    }
    const response = mw("next", NextResponse.next());
    const session = await auth0Edge().getSession(request, response);
    if (!session) {
      const targetPath = `${pathname}${request.nextUrl.search || ""}` || "/console";
      const returnTo = sanitizeReturnTo(targetPath, "/console");
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = "/auth/login";
      loginUrl.search = `returnTo=${encodeURIComponent(returnTo)}`;
      return mw("redirect:/auth/login", NextResponse.redirect(loginUrl));
    }
    return response;
  }

  if (pathname.startsWith("/admin")) {
    if (!authConfigured) {
      return rewriteTo404();
    }
    return mw("next", NextResponse.next());
  }

  return mw("next", NextResponse.next());
}

export const config = {
  matcher: [
    "/admin/:path*",
    "/chat/:path*",
    "/runs/:path*",
    "/console/:path*",
    "/dev/:path*",
    "/demo",
    "/demo/:path*",
    "/_demo",
    "/_demo/:path*",
  ],
};
