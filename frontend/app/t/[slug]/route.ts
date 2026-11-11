import { relayPublicPage } from "@/lib/server-api";

/** La première étape d'un tunnel publié, servie comme document entier. */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const source = new URL(request.url).searchParams.get("source") || new URL(request.url).searchParams.get("utm_source") || "";
  const query = source ? `&source=${encodeURIComponent(source)}` : "";
  return relayPublicPage(`/public/sales/${encodeURIComponent(slug)}/document?step=1${query}`, request);
}
