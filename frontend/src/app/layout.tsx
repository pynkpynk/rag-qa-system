import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG QA Frontend",
  description: "Status surface for the RAG QA System API",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
