import { relayPublicPage } from "@/lib/server-api";

/** La première étape d'un tunnel publié, servie comme document entier. */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const query = new URL(request.url).searchParams;
  const source = query.get("source") || query.get("utm_source") || "";
  const suffix = source ? `?source=${encodeURIComponent(source)}` : "";
  return relayPublicPage(`/public/sales/${encodeURIComponent(slug)}/document${suffix}`, request);
}
