import type { ReactElement } from "react";
import { redirect } from "next/navigation";
import { getAuth0, isAuthConfigured } from "@/lib/auth0";
import HomeClient from "./home-client";

export const dynamic = "force-dynamic";

export default async function HomePage(): Promise<ReactElement> {
  if (!isAuthConfigured) {
    return <HomeClient />;
  }

  const session = await getAuth0().getSession();
  if (!session) {
    redirect("/auth/login");
  }

  redirect("/chat");
}
