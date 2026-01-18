import type { ReactElement } from "react";
import ConsolePage from "../console/page";

export const dynamic = "force-dynamic";

export default function DemoInternalPage(): ReactElement {
  return <ConsolePage />;
}
