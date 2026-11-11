import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/server-api";

/** Les tunnels publiés sont faits pour être trouvés ; le reste ne l'est pas. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/t/", disallow: ["/campaigns", "/dashboard", "/responses", "/library", "/settings", "/team", "/funnels", "/forms/"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
