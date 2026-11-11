import type { MetadataRoute } from "next";
import { SERVER_API_URL, SITE_URL } from "@/lib/server-api";

type Published = { slug: string; updated_at: string };

/** Les tunnels en ligne. Une API indisponible rend un sitemap vide plutôt
 *  qu'une erreur : mieux vaut ne rien annoncer qu'un plan du site faux. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  try {
    const response = await fetch(`${SERVER_API_URL}/public/sales-sitemap`, { cache: "no-store" });
    if (!response.ok) return [];
    const published: Published[] = await response.json();
    return published.map(item => ({
      url: `${SITE_URL}/t/${item.slug}`,
      lastModified: new Date(item.updated_at),
      changeFrequency: "weekly" as const,
      priority: 0.8,
    }));
  } catch {
    return [];
  }
}
