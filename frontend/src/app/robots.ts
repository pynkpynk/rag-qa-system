import type { MetadataRoute } from "next";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL &&
  /^https?:\/\//i.test(process.env.NEXT_PUBLIC_SITE_URL)
    ? process.env.NEXT_PUBLIC_SITE_URL
    : undefined;

export default function robots(): MetadataRoute.Robots {
  const robots: MetadataRoute.Robots = {
    rules: [
      {
        userAgent: "*",
        allow: "/",
      },
    ],
  };
  if (SITE_URL) {
    robots.sitemap = `${SITE_URL.replace(/\/$/, "")}/sitemap.xml`;
  }
  return robots;
}
