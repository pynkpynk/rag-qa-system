import { redirect } from "next/navigation";
import TokenGate from "../../components/TokenGate";
import HomeClient from "../home-client";

export const dynamic = "force-dynamic";

export default function DemoPage() {
  if (process.env.DEMO_ENTRY_ENABLED !== "1") {
    redirect("/");
  }
  return (
    <TokenGate>
      <HomeClient />
    </TokenGate>
  );
}
