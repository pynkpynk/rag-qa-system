import { notFound } from "next/navigation";
import DevClient from "./DevClient";

export default function DevPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return <DevClient />;
}
