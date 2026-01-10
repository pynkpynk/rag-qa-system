import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { getAuth0, isAuthConfigured } from "@/lib/auth0";

export const dynamic = "force-dynamic";

export default async function ChatLayout({
  children,
}: {
  children: ReactNode;
}) {
  if (!isAuthConfigured) {
    return <>{children}</>;
  }

  const session = await getAuth0().getSession();

  if (!session?.user) {
    const returnTo = "/chat";
    redirect(`/auth/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  return <>{children}</>;
}
