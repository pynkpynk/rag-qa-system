import type { ReactElement } from "react";
import HomeClient from "../home-client";

export const dynamic = "force-dynamic";

export default function ConsolePage(): ReactElement {
  return <HomeClient />;
}
