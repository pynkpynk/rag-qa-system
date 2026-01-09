import type { Session } from "@auth0/nextjs-auth0";

function parseList(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function isAdminSession(session: Session | null | undefined): boolean {
  const emailAllowlist = parseList(
    process.env.ADMIN_EMAIL_ALLOWLIST ?? process.env.ADMIN_EMAILS,
  ).map((item) => item.toLowerCase());
  const subAllowlist = parseList(
    process.env.ADMIN_SUB_ALLOWLIST ?? process.env.ADMIN_SUBS,
  );

  if (!emailAllowlist.length && !subAllowlist.length) {
    return false;
  }

  const user = session?.user;
  if (!user) return false;

  const email = user.email?.toLowerCase();
  const sub = user.sub;

  if (email && emailAllowlist.includes(email)) {
    return true;
  }
  if (sub && subAllowlist.includes(sub)) {
    return true;
  }
  return false;
}
