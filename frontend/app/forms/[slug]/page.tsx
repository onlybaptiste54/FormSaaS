"use client";

import { use, useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { PageFrame } from "@/components/page-frame";
import { API_URL } from "@/lib/api";
import type { PageField } from "@/lib/types";

type TunnelPage = {
  id: string;
  role: "landing" | "form" | "thanks" | "step" | "custom";
  position: number;
  next_page_id: string | null;
  visits: number;
  conversions: number;
};

type PublicCampaign = {
  name: string;
  thank_you: Record<string, string>;
  html: string;
  thanks_html: string;
  manifest: PageField[];
  status: string;
  tunnel?: { id: string; entry_page_id: string; pages: TunnelPage[] };
};

type JourneyPage = {
  page_id: string | null;
  html: string;
  manifest: PageField[];
  next_page_id: string | null;
};

type JourneyResponse = Omit<JourneyPage, "page_id"> & { page_id: string };

async function publicApi<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : "Cette étape est indisponible.");
  }
  return response.json();
}

export default function PublicForm({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [campaign, setCampaign] = useState<PublicCampaign | null>(null);
  const [currentPage, setCurrentPage] = useState<JourneyPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [journeyReady, setJourneyReady] = useState(false);
  const [preview, setPreview] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setJourneyReady(false);
    const isPreview = new URLSearchParams(location.search).get("preview") === "1";
    setPreview(isPreview);
    publicApi<PublicCampaign>(`/public/${slug}`)
      .then(async data => {
        if (cancelled) return;
        const entryId = data.tunnel?.entry_page_id ?? null;
        const entry = data.tunnel?.pages.find(page => page.id === entryId);
        setCampaign(data);
        setCurrentPage({ page_id: entryId, html: data.html, manifest: data.manifest, next_page_id: entry?.next_page_id ?? null });
        if (data.status !== "active" || isPreview) return;
        try {
          const visited = await publicApi<JourneyResponse>(`/public/${slug}/visit`, { page_id: entryId });
          if (!cancelled) {
            setCurrentPage(visited);
            setJourneyReady(true);
          }
        } catch (err) {
          if (!cancelled) setError(err instanceof Error ? err.message : "Cette étape est indisponible.");
        }
      })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : "Formulaire indisponible."); });
    return () => { cancelled = true; };
  }, [slug]);

  // La redirection choisie dans le tunnel garde son délai et son lien de secours.
  useEffect(() => {
    if (!done || campaign?.thank_you.action !== "redirect" || !campaign.thank_you.button_url) return;
    const timer = setTimeout(() => { location.href = campaign.thank_you.button_url; }, 3000);
    return () => clearTimeout(timer);
  }, [done, campaign]);

  async function advance() {
    if (!campaign || !currentPage?.page_id || !currentPage.next_page_id || !journeyReady || busy || submitting.current || campaign.status !== "active") return;
    setBusy(true);
    setError("");
    try {
      const page = await publicApi<JourneyResponse>(`/public/${slug}/advance`, { from_page_id: currentPage.page_id });
      setCurrentPage(page);
      setDone(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d’ouvrir cette étape.");
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswers(answersToSend: Record<string, string | number>, consentToSend: boolean) {
    if (!campaign || !currentPage) return;
    for (const field of currentPage.manifest) {
      if (field.type === "consent" || !field.required) continue;
      if (answersToSend[field.name] === undefined || answersToSend[field.name] === "") {
        setError(`Le champ « ${field.label} » est requis.`);
        return;
      }
    }
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    const query = new URLSearchParams(location.search);
    try {
      const submitted = await publicApi<{ next_page_id: string | null; thanks_html: string; html: string; manifest: PageField[]; journey_token: string }>(`/public/${slug}/submit`, {
        page_id: currentPage.page_id,
        answers: answersToSend,
        consent: consentToSend,
        source: query.get("source") || "Lien direct",
        promo_code: query.get("promo") || "",
      });
      const next = campaign.tunnel?.pages.find(page => page.id === submitted.next_page_id);
      setCurrentPage({ page_id: submitted.next_page_id, html: submitted.html || submitted.thanks_html, manifest: submitted.manifest, next_page_id: next?.next_page_id ?? null });
      setDone(!next || next.role === "thanks");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Envoi impossible");
    } finally {
      setBusy(false);
      submitting.current = false;
    }
  }

  function submitDocument(form: HTMLFormElement, data: FormData) {
    if (!campaign || !currentPage || campaign.status !== "active" || !journeyReady || busy) return;
    const consentField = form.querySelector<HTMLInputElement>('[data-sillage="consent"] input[type="checkbox"]');
    const values: Record<string, string | number> = {};
    for (const [name, value] of data.entries()) {
      if (name && typeof value === "string" && name !== "consent" && name !== consentField?.name) values[name] = value;
    }
    const accepted = consentField?.checked ?? data.get("consent") === "on";
    void submitAnswers(values, accepted);
  }

  if (error && !campaign) return <main className="public-form-page"><div className="public-error-card"><h1>Formulaire indisponible</h1><p>{error}</p></div></main>;
  if (!campaign || !currentPage) return <main className="public-form-page"><LoaderCircle className="spin"/></main>;

  return <main className="public-document-page">
    {campaign.status !== "active" && <div className="public-draft-banner">Aperçu d’un brouillon : ce formulaire n’accepte pas encore de réponse.</div>}
    <PageFrame
      html={currentPage.html}
      title={`${campaign.name}${done ? " — Merci" : ""}`}
      mode="public"
      onSubmit={submitDocument}
      onNext={advance}
    />
    {busy && <p className="public-document-status">{submitting.current ? "Envoi en cours…" : "Ouverture de l’étape…"}</p>}
    {campaign.status === "active" && !preview && !journeyReady && !error && <p className="public-document-status">Préparation du parcours…</p>}
    {error && <p className="public-document-status form-error" role="alert">{error}</p>}
  </main>;
}
