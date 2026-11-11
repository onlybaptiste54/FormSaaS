import { relayPublicPage } from "@/lib/server-api";

/** Les étapes suivantes, et « go » qui enregistre le clic final puis renvoie. */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string; step: string }> }) {
  const { slug, step } = await params;
  const base = `/public/sales/${encodeURIComponent(slug)}`;
  if (step === "go") return relayPublicPage(`${base}/go`, request);
  if (!/^[1-9][0-9]?$/.test(step)) return new Response("Étape introuvable", { status: 404 });
  return relayPublicPage(`${base}/document?step=${step}`, request);
}
