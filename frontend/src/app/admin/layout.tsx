import type { ReactNode } from "react";
import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getAuth0, isAuthConfigured } from "@/lib/auth0";
import { isAdminSession } from "@/lib/admin";

export const dynamic = "force-dynamic";

function currentPath(): string {
  const headerList = headers();
  const headerUrl =
    headerList.get("next-url") ||
    headerList.get("referer") ||
    "/admin";
  return headerUrl;
}

export default async function AdminLayout({
  children,
}: {
  children: ReactNode;
}) {
  if (!isAuthConfigured) {
    notFound();
  }

  const session = await getAuth0().getSession();

  if (!session) {
    const returnTo = currentPath();
    redirect(`/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  if (!isAdminSession(session)) {
    notFound();
  }

  return <>{children}</>;
}
