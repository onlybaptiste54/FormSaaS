"use client";

import { FormEvent, use, useEffect, useState } from "react";
import { Check, ChevronDown, LoaderCircle, Send } from "lucide-react";
import { api } from "@/lib/api";
import { backgroundClassName, designClassNames, formStyleVars } from "@/lib/form-design";
import { thankYouTitle } from "@/lib/form-text";
import type { Field, FormDesign } from "@/lib/types";

type PublicCampaign = {
  name: string;
  description: string;
  fields: Field[];
  design: FormDesign;
  thank_you: Record<string, string>;
  status: string;
  company: { name: string; legal_name: string; address: string; primary_color: string; accent_color: string; dpo_email: string };
};

type Answers = Record<string, string | number>;

export default function PublicForm({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [campaign, setCampaign] = useState<PublicCampaign | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
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

  function missingFields(): Record<string, string> {
    if (!campaign) return {};
    const errors: Record<string, string> = {};
    for (const field of campaign.fields) {
      if (field.type === "consent" || !field.required) continue;
      const value = answers[field.id];
      if (value === undefined || value === "") errors[field.id] = "Ce champ est requis";
    }
    return errors;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const errors = missingFields();
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

  const style = { ...formStyleVars(campaign.design), "--client": campaign.company.primary_color, "--client-accent": campaign.company.accent_color } as React.CSSProperties;
  const pageClass = `public-form-page ${backgroundClassName(campaign.design)}`;
  const formClass = `public-card ${designClassNames(campaign.design)}`;
  const monogram = campaign.company.name.split(" ").map(word => word[0]).join("").slice(0, 2);
  const legal = <footer>{campaign.company.legal_name} · {campaign.company.address}{campaign.company.dpo_email && <> · <a href={`mailto:${campaign.company.dpo_email}`}>Vos données</a></>}</footer>;

  if (done) return <main className={pageClass} style={style}>
    <div className={`${formClass} thank-you-card`}>
      <div className="public-brand"><span>{monogram}</span><strong>{campaign.company.name}</strong></div>
      <div className="thanks-check"><Check/></div>
      <h1>{thankYouTitle(campaign.thank_you.title, answers)}</h1>
      <p>{campaign.thank_you.message}</p>
      {campaign.thank_you.action !== "none" && campaign.thank_you.button_url && <a href={campaign.thank_you.button_url} className="public-submit">{campaign.thank_you.button_label || "Continuer"}</a>}
      {campaign.thank_you.action === "redirect" && <p className="secure-note">Redirection en cours…</p>}
      {legal}
    </div>
  </main>;

  return <main className={pageClass} style={style}>
    {campaign.status !== "active" && <div className="public-draft-banner">Aperçu d’un brouillon : ce formulaire n’accepte pas encore de réponse.</div>}
    <form className={formClass} onSubmit={submit} noValidate>
      <div className="public-brand"><span>{monogram}</span><strong>{campaign.company.name}</strong></div>
      <header><h1>{campaign.name}</h1><p>{campaign.description}</p></header>
      <div className="public-fields">
        {campaign.fields.map(field => field.type === "consent" ? (
          <label className="public-consent" key={field.id}>
            <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} required={field.required}/>
            <span><i><Check size={13}/></i>{field.label}</span>
          </label>
        ) : (
          <PublicField
            key={field.id}
            field={field}
            value={answers[field.id] ?? ""}
            error={invalid[field.id]}
            onChange={value => { setAnswers({ ...answers, [field.id]: value }); setInvalid(({ [field.id]: _removed, ...rest }) => rest); }}
          />
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="public-submit" disabled={busy || campaign.status !== "active"}>{busy ? <><LoaderCircle className="spin" size={18}/>Envoi en cours…</> : <>Envoyer ma réponse <Send size={17}/></>}</button>
      <p className="secure-note">Vos données sont protégées et utilisées uniquement pour traiter votre demande.</p>
      {legal}
    </form>
  </main>;
}

function PublicField({ field, value, error, onChange }: { field: Field; value: string | number; error?: string; onChange: (value: string | number) => void }) {
  const label = <>{field.label}{field.required && " *"}</>;
  const hint = error && <span className="field-error">{error}</span>;

  if (field.type === "rating") return <div className="public-field" data-field={field.id}>
    <label>{label}</label>
    <div className="public-rating">{Array.from({ length: field.scale || 5 }, (_, index) => index + 1).map(note => <button type="button" key={note} aria-pressed={value === note} className={value === note ? "selected" : ""} onClick={() => onChange(note)}>{note}</button>)}</div>
    {hint}
  </div>;

  if (field.type === "radio") return <div className="public-field" data-field={field.id}>
    <label>{label}</label>
    <div className="public-options">{field.options?.map(option => <button type="button" key={option} aria-pressed={value === option} className={value === option ? "selected" : ""} onClick={() => onChange(option)}>{option}</button>)}</div>
    {hint}
  </div>;

  if (field.type === "select") return <label className="public-field" data-field={field.id}>
    {label}
    <div className="select-wrap"><select value={value} onChange={event => onChange(event.target.value)}><option value="">Sélectionnez une option</option>{field.options?.map(option => <option key={option}>{option}</option>)}</select><ChevronDown/></div>
    {hint}
  </label>;

  if (field.type === "textarea") return <label className="public-field" data-field={field.id}>
    {label}
    <textarea value={value} onChange={event => onChange(event.target.value)}/>
    {hint}
  </label>;

  return <label className="public-field" data-field={field.id}>
    {label}
    <input type={field.type === "tel" ? "tel" : field.type} value={value} placeholder={field.placeholder} onChange={event => onChange(event.target.value)}/>
    {hint}
  </label>;
}
