import { notFound, redirect } from "next/navigation";
import DevClient from "./DevClient";
import { getAuth0, isAuthConfigured } from "@/lib/auth0";
import { isAdminSession } from "@/lib/admin";

export const dynamic = "force-dynamic";

export default async function DevPage() {
  const allowDevRoutes = process.env.ALLOW_DEV_ROUTES === "1";
  const inProduction = process.env.NODE_ENV === "production";

  if (inProduction && !allowDevRoutes) {
    notFound();
  }

  if (!inProduction) {
    return <DevClient />;
  }

  if (!isAuthConfigured) {
    notFound();
  }

  const session = await getAuth0().getSession();

  if (!session) {
    redirect(`/auth/login?returnTo=${encodeURIComponent("/dev")}`);
  }

  if (!isAdminSession(session)) {
    notFound();
  }

  return <DevClient />;
}
