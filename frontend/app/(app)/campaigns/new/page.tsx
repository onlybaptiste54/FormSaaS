"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, LoaderCircle, MessageCircle, Sparkles } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

const suggestions = [
  "Un formulaire de contact pour mon activité",
  "Un sondage de satisfaction après une visite",
  "Une inscription pour mon prochain événement",
];

/** Étapes affichées pendant la génération : Luna ne streame pas encore. */
const steps = ["J’analyse votre brief…", "Je choisis les champs utiles…", "J’applique votre identité visuelle…"];

export default function NewCampaignPage() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (prompt.trim().length < 10) return;
    setBusy(true);
    setError("");
    setStep(0);
    timer.current = setInterval(() => setStep(current => Math.min(current + 1, steps.length - 1)), 4000);
    try {
      const campaign = await api<Campaign>("/campaigns", { method: "POST", body: JSON.stringify({ prompt }) });
      router.push(`/campaigns/${campaign.id}?tab=form`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible");
      setBusy(false);
    } finally {
      if (timer.current) clearInterval(timer.current);
    }
  }

  return <div className="creation-page">
    <div className="creation-top">
      <Link href="/campaigns" className="back-link"><ArrowLeft size={18}/>Retour aux campagnes</Link>
      <div className="step-indicator"><span className="current">Brief</span><i/><span>Aperçu</span><i/><span>Publication</span></div>
    </div>
    <section className="luna-stage">
      <div className="luna-symbol"><Sparkles size={24}/></div>
      <p className="eyebrow">LUNA · CRÉATION ASSISTÉE</p>
      <h1>Que souhaitez-vous créer&nbsp;?</h1>
      <p className="creation-intro">Décrivez simplement votre besoin. Je m’occupe des champs, du texte et de la conformité.</p>
      <form onSubmit={create} className="prompt-form">
        <div className="prompt-box">
          <MessageCircle size={20}/>
          <textarea value={prompt} onChange={event => setPrompt(event.target.value)} maxLength={1200} placeholder="Ex. Je veux un formulaire de contact pour mon entreprise de plomberie. J’aimerais connaître le type d’intervention et son niveau d’urgence…" autoFocus/>
          <span>{prompt.length}/1200</span>
        </div>
        {error && <p className="form-error">{error}</p>}
        <button className="button button-primary button-large" disabled={busy || prompt.trim().length < 10}>
          {busy ? <><LoaderCircle className="spin" size={19}/>{steps[step]}</> : <>Créer ma campagne <ArrowRight size={18}/></>}
        </button>
      </form>
      <div className="suggestions"><span>Ou partez d’une idée</span>{suggestions.map(item => <button type="button" key={item} onClick={() => setPrompt(item)}>{item}</button>)}</div>
      <div className="creation-reassurance"><span><Check size={16}/>5 champs maximum, plus le consentement</span><span><Check size={16}/>Opt-in RGPD natif</span><span><Check size={16}/>Adapté à votre identité</span></div>
    </section>
  </div>;
}
