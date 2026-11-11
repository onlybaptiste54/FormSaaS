import { relayPublicPage } from "@/lib/server-api";

/** Une étape nommée, et « go » qui enregistre le clic final puis redirige. */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string; step: string }> }) {
  const { slug, step } = await params;
  const base = `/public/sales/${encodeURIComponent(slug)}`;
  if (step === "go") return relayPublicPage(`${base}/go`, request);
  return relayPublicPage(`${base}/document?step=${encodeURIComponent(step)}`, request);
}
