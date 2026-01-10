import type { ConfigParameters } from "@auth0/nextjs-auth0";

const isProdRuntime =
  process.env.NODE_ENV === "production" &&
  process.env.NEXT_PHASE !== "phase-production-build";

function baseUrl(): string {
  const raw =
    process.env.AUTH0_BASE_URL ||
    process.env.NEXT_PUBLIC_SITE_URL ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : undefined) ||
    "http://localhost:3000";
  return raw.replace(/\/$/, "");
}

function issuerUrl(): string | undefined {
  if (process.env.AUTH0_ISSUER_BASE_URL) {
    return process.env.AUTH0_ISSUER_BASE_URL.replace(/\/$/, "");
  }
  if (process.env.AUTH0_DOMAIN) {
    const domain = process.env.AUTH0_DOMAIN.replace(/^https?:\/\//, "");
    return `https://${domain}`;
  }
  return undefined;
}

function requireValue(value: string | undefined, label: string): string {
  if (value) {
    return value;
  }
  const message = `[auth0] Missing ${label} env var.`;
  if (isProdRuntime) {
    throw new Error(message);
  }
  console.warn(message);
  return `missing-${label}`;
}

const hasIssuer = Boolean(process.env.AUTH0_ISSUER_BASE_URL || process.env.AUTH0_DOMAIN);
const hasClient =
  Boolean(process.env.AUTH0_CLIENT_ID) && Boolean(process.env.AUTH0_CLIENT_SECRET);
const hasSecret = Boolean(process.env.AUTH0_SECRET);

export const isAuthConfigured = hasIssuer && hasClient && hasSecret;

export function buildAuth0Config(): ConfigParameters {
  return {
    baseURL: baseUrl(),
    issuerBaseURL: requireValue(
      issuerUrl(),
      "AUTH0_ISSUER_BASE_URL or AUTH0_DOMAIN",
    ),
    clientID: requireValue(process.env.AUTH0_CLIENT_ID, "AUTH0_CLIENT_ID"),
    clientSecret: requireValue(
      process.env.AUTH0_CLIENT_SECRET,
      "AUTH0_CLIENT_SECRET",
    ),
    secret: requireValue(process.env.AUTH0_SECRET, "AUTH0_SECRET"),
    routes: {
      login: "/auth/login",
      callback: "/auth/callback",
      postLogoutRedirect: "/",
    },
  };
}
