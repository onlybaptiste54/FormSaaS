"use client";

import { FormEvent, use, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { FormRenderer, FormStage } from "@/components/form-renderer";
import { api } from "@/lib/api";
import type { Field, FormContent, FormDesign } from "@/lib/types";

type PublicCampaign = {
  name: string;
  description: string;
  fields: Field[];
  design: FormDesign;
  content: FormContent;
  thank_you: Record<string, string>;
  status: string;
  company: { name: string; legal_name: string; address: string; primary_color: string; accent_color: string; dpo_email: string };
};

export default function PublicForm({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [campaign, setCampaign] = useState<PublicCampaign | null>(null);
  const [answers, setAnswers] = useState<Record<string, string | number>>({});
  const [consent, setConsent] = useState(false);
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<PublicCampaign>(`/public/${slug}`).then(setCampaign).catch(err => setError(err.message));
  }, [slug]);

  // Une visite par session et par formulaire : un rechargement ou un apercu
  // interne ne doit pas gonfler la conversion.
  useEffect(() => {
    if (!campaign || campaign.status !== "active") return;
    if (new URLSearchParams(location.search).get("preview") === "1") return;
    const key = `sillage-visit-${slug}`;
    try {
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, "1");
    } catch {
      // Stockage indisponible : on compte la visite, sans dedoublonnage.
    }
    void api(`/public/${slug}/visit`, { method: "POST" }).catch(() => undefined);
  }, [campaign, slug]);

  // Redirection automatique configuree dans le tunnel, avec lien de secours.
  useEffect(() => {
    if (!done || campaign?.thank_you.action !== "redirect" || !campaign.thank_you.button_url) return;
    const timer = setTimeout(() => { location.href = campaign.thank_you.button_url; }, 3000);
    return () => clearTimeout(timer);
  }, [done, campaign]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!campaign) return;
    const errors: Record<string, string> = {};
    for (const field of campaign.fields) {
      if (field.type === "consent" || !field.required) continue;
      if (answers[field.id] === undefined || answers[field.id] === "") errors[field.id] = "Ce champ est requis";
    }
    setInvalid(errors);
    if (Object.keys(errors).length) {
      document.querySelector(`[data-field="${Object.keys(errors)[0]}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setBusy(true);
    setError("");
    const query = new URLSearchParams(location.search);
    try {
      await api(`/public/${slug}/submit`, {
        method: "POST",
        body: JSON.stringify({ answers, consent, source: query.get("source") || "Lien direct", promo_code: query.get("promo") || "" }),
      });
      setDone(true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Envoi impossible");
      setBusy(false);
    }
  }

  if (error && !campaign) return <main className="public-form-page"><div className="public-card"><h1>Formulaire indisponible</h1><p>{error}</p></div></main>;
  if (!campaign) return <main className="public-form-page"><LoaderCircle className="spin"/></main>;

  return <FormStage as="main" design={campaign.design} className="public-form-page" style={{ "--client": campaign.company.primary_color, "--client-accent": campaign.company.accent_color } as React.CSSProperties}>
    {campaign.status !== "active" && <div className="public-draft-banner">Aperçu d’un brouillon : ce formulaire n’accepte pas encore de réponse.</div>}
    {done ? (
      <FormRenderer form={campaign} company={campaign.company} mode="public" view="thanks" values={answers}/>
    ) : (
      <FormRenderer
        form={campaign}
        company={campaign.company}
        mode="public"
        values={answers}
        consent={consent}
        errors={invalid}
        busy={busy || campaign.status !== "active"}
        error={error}
        onChange={(id, value) => { setAnswers({ ...answers, [id]: value }); setInvalid(({ [id]: _removed, ...rest }) => rest); }}
        onConsent={setConsent}
        onSubmit={submit}
      />
    )}
  </FormStage>;
}
