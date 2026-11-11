import type { Metadata } from "next";
import { PublicSalesFunnel } from "./funnel";
import { SERVER_API_URL, SITE_URL } from "@/lib/server-api";

type Reference = { title: string; description: string };

const SITE_NAME = "Sillage";

/** Référence d'un tunnel publié, ou rien s'il n'est pas en ligne. */
async function reference(slug: string): Promise<Reference | null> {
  try {
    const response = await fetch(`${SERVER_API_URL}/public/sales/${encodeURIComponent(slug)}/meta`, { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const found = await reference(slug);
  if (!found) return { title: "Tunnel indisponible", robots: { index: false, follow: false } };
  const url = `${SITE_URL}/t/${slug}`;
  return {
    title: found.title,
    description: found.description || undefined,
    alternates: { canonical: url },
    openGraph: { title: found.title, description: found.description || undefined, url, type: "website", siteName: SITE_NAME },
    twitter: { card: "summary_large_image", title: found.title, description: found.description || undefined },
  };
}

export default async function PublicSalesFunnelPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <PublicSalesFunnel slug={slug}/>;
}
