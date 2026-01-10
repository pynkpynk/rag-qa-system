import { notFound } from "next/navigation";
import DevClient from "@/app/dev/DevClient";

export const dynamic = "force-dynamic";

export default function AdminDevPage() {
  const allowDevRoutes = process.env.ALLOW_DEV_ROUTES === "1";
  const inProduction = process.env.NODE_ENV === "production";

  if (inProduction && !allowDevRoutes) {
    notFound();
  }

  return <DevClient />;
}
