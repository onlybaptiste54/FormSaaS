"use client";

import { use, useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { PageFrame } from "@/components/page-frame";
import { API_URL } from "@/lib/api";

type PublicStep = { page_id: string; name: string; role: string; next_page_id: string | null; html: string };

async function journey<T>(path: string, body: object = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Ce tunnel est indisponible.");
  }
  return response.json();
}

export default function PublicSalesFunnel({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [page, setPage] = useState<PublicStep | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const loading = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const query = new URLSearchParams(window.location.search);
    const source = query.get("source") || query.get("utm_source") || "Lien direct";
    void journey<PublicStep>(`/public/sales/${slug}/visit`, { source: source.slice(0, 80) })
      .then(result => { if (!cancelled) setPage(result); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Tunnel indisponible"); });
    return () => { cancelled = true; };
  }, [slug]);

  async function advance() {
    if (loading.current || !page?.next_page_id) return;
    loading.current = true; setBusy(true); setError("");
    try { setPage(await journey<PublicStep>(`/public/sales/${slug}/advance`)); window.scrollTo({ top: 0, behavior: "smooth" }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Impossible d’ouvrir cette étape."); }
    finally { loading.current = false; setBusy(false); }
  }

  async function goal() {
    if (loading.current) return;
    loading.current = true; setBusy(true); setError("");
    try { const result = await journey<{ url: string }>(`/public/sales/${slug}/goal`); window.location.assign(result.url); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Impossible d’ouvrir le lien."); loading.current = false; setBusy(false); }
  }

  if (error && !page) return <main className="public-form-page"><div className="public-error-card"><h1>Tunnel indisponible</h1><p>{error}</p></div></main>;
  if (!page) return <main className="public-form-page"><LoaderCircle className="spin"/></main>;
  return <main className="public-document-page"><PageFrame html={page.html} title={page.name} mode="public" onNext={() => void advance()} onGoal={() => void goal()}/>{busy && <p className="public-document-status">Ouverture en cours…</p>}{error && <p className="public-document-status form-error" role="alert">{error}</p>}</main>;
}
