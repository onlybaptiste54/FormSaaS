"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, ImagePlus, LoaderCircle, MessageCircle, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useMe } from "@/components/shell";
import { api } from "@/lib/api";
import { readImageAsDataUrl } from "@/lib/image";
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
  const me = useMe();
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [useBrand, setUseBrand] = useState(true);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  async function addImage(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const dataUrl = await readImageAsDataUrl(file, 1400);
      setImages(current => [...current, dataUrl].slice(0, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image illisible");
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (prompt.trim().length < 10) return;
    setBusy(true);
    setError("");
    setStep(0);
    timer.current = setInterval(() => setStep(current => Math.min(current + 1, steps.length - 1)), 4000);
    try {
      const campaign = await api<Campaign>("/campaigns", { method: "POST", body: JSON.stringify({ prompt, context, images, use_brand: useBrand }) });
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
        <details className="creation-context">
          <summary>Contexte pour Luna <small>facultatif</small></summary>
          <textarea value={context} maxLength={800} placeholder="Ex. c’est pour nos portes ouvertes du 12 octobre, le ton doit rester familial." onChange={event => setContext(event.target.value)}/>
          <div className="brand-dropzone">
            {images.map((image, index) => <div className="brand-thumb" key={image.slice(-24)}>
              <img src={image} alt={`Référence ${index + 1}`}/>
              <button type="button" onClick={() => setImages(current => current.filter((_, position) => position !== index))} aria-label="Retirer cette image"><X size={13}/></button>
            </div>)}
            {images.length < 2 && <label className="brand-add">
              <ImagePlus size={18}/><span>Image de référence</span>
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void addImage(event)} hidden/>
            </label>}
          </div>
        </details>
        {error && <p className="form-error">{error}</p>}
        <button className="button button-primary button-large" disabled={busy || prompt.trim().length < 10}>
          {busy ? <><LoaderCircle className="spin" size={19}/>{steps[step]}</> : <>Créer ma campagne <ArrowRight size={18}/></>}
        </button>
      </form>
      <div className="suggestions"><span>Ou partez d’une idée</span>{suggestions.map(item => <button type="button" key={item} onClick={() => setPrompt(item)}>{item}</button>)}</div>
      <button type="button" className={`brand-toggle ${useBrand ? "on" : ""}`} onClick={() => setUseBrand(value => !value)}>
        <i>{useBrand && <Check size={12}/>}</i>
        {me?.company.brand?.summary || me?.company.brand?.palette?.length
          ? `Charte de ${me.company.name} appliquée`
          : `Identité de ${me?.company.name || "votre entreprise"} appliquée`}
      </button>
      <div className="creation-reassurance"><span><Check size={16}/>5 champs maximum, plus le consentement</span><span><Check size={16}/>Opt-in RGPD natif</span><span><Check size={16}/>Adapté à votre identité</span></div>
    </section>
  </div>;
}
