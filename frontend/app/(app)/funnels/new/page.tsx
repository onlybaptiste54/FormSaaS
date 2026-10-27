"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, ExternalLink, LoaderCircle, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useMe } from "@/components/shell";
import type { SalesTunnel } from "@/lib/types";

type Brief = { name: string; offer: string; audience: string; benefits: string[]; proof: string; tone: string; goal_label: string; goal_url: string; website_url: string };
const initial: Brief = { name: "", offer: "", audience: "", benefits: ["", "", ""], proof: "", tone: "", goal_label: "Prendre rendez-vous", goal_url: "", website_url: "" };

export default function NewSalesFunnel() {
  const router = useRouter();
  const me = useMe();
  const [brief, setBrief] = useState<Brief>(initial);
  const [stage, setStage] = useState(0);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { void api<{ configured: boolean }>("/luna/status").then(result => setConfigured(result.configured)).catch(() => setConfigured(false)); }, []);
  const change = (key: keyof Brief, value: string) => setBrief(current => ({ ...current, [key]: value }));
  const benefits = brief.benefits.map(item => item.trim()).filter(Boolean);
  const canContinue = stage === 0 ? brief.name.trim().length >= 3 && brief.offer.trim().length >= 10
    : stage === 1 ? brief.audience.trim().length >= 10 && benefits.length > 0
    : brief.goal_label.trim().length >= 3 && /^https:\/\/[^\s]+$/i.test(brief.goal_url.trim());

  async function next(event: FormEvent) {
    event.preventDefault();
    if (!canContinue || busy) return;
    setError("");
    if (stage < 2) { setStage(stage + 1); return; }
    setBusy(true);
    try {
      const tunnel = await api<SalesTunnel>("/sales-funnels", { method: "POST", body: JSON.stringify({ ...brief, benefits }) });
      router.push(`/funnels/${tunnel.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "La création du tunnel a échoué.");
      setBusy(false);
    }
  }

  return <div className="page-wrap sales-wizard">
    <Link href="/funnels" className="back-link"><ArrowLeft size={17}/>Tunnels de vente</Link>
    <div className="sales-wizard-hero"><span className="sales-kicker"><Sparkles size={16}/>LUNA · CRÉATION GUIDÉE</span><h1>Construisons votre tunnel de vente.</h1><p>Quelques réponses concrètes suffisent. Luna créera les pages ; vous pourrez les corriger avant publication.</p></div>
    <div className="sales-progress" aria-label="Progression">{["L’offre", "Les arguments", "L’action"].map((label, index) => <span key={label} className={index === stage ? "current" : index < stage ? "done" : ""}><b>{index < stage ? <Check size={13}/> : index + 1}</b>{label}</span>)}</div>
    <form className="panel sales-wizard-card" onSubmit={event => void next(event)}>
      {stage === 0 && <>
        <p className="eyebrow">ÉTAPE 1 / 3</p><h2>Que vendez-vous ?</h2><p className="sales-help">Parlez de l’offre comme vous l’expliqueriez à un nouveau client. Luna n’inventera ni prix ni promesse.</p>
        <label>Nom du tunnel<input value={brief.name} maxLength={140} required minLength={3} placeholder="Ex. Découverte de notre accompagnement" onChange={event => change("name", event.target.value)}/><small>Ce nom sert à retrouver le tunnel dans votre espace.</small></label>
        <label>Votre offre<textarea value={brief.offer} maxLength={500} required minLength={10} placeholder="Ex. Un accompagnement de 6 semaines pour aider les artisans à trouver leurs premiers clients en ligne." onChange={event => change("offer", event.target.value)}/><small>Indiquez ce qui est inclus et le résultat recherché. Ajoutez le prix si vous souhaitez l’afficher.</small></label>
        <div className="sales-brand-note">Marque appliquée : <strong>{me?.company.name || "votre entreprise"}</strong>. Vous pourrez modifier ses couleurs et son ton dans les paramètres.</div>
      </>}
      {stage === 1 && <>
        <p className="eyebrow">ÉTAPE 2 / 3</p><h2>Pourquoi choisir votre offre ?</h2><p className="sales-help">Ces éléments nourrissent la page de vente. Gardez seulement des affirmations que vous pouvez soutenir.</p>
        <label>À qui s’adresse-t-elle ?<textarea value={brief.audience} maxLength={300} required minLength={10} placeholder="Ex. Aux indépendants qui ont déjà une offre, mais peu de demandes entrantes." onChange={event => change("audience", event.target.value)}/></label>
        <label>Vos points forts<small>Un avantage précis par ligne</small>{brief.benefits.map((benefit, index) => <input key={index} value={benefit} maxLength={180} placeholder={["Ex. Un diagnostic individuel dès le premier échange", "Ex. Un plan d’action adapté à l’activité", "Ex. Un suivi chaque semaine"][index]} onChange={event => setBrief(current => ({ ...current, benefits: current.benefits.map((item, position) => position === index ? event.target.value : item) }))}/>)}</label>
        <label>Preuve ou élément de confiance <small>facultatif</small><textarea value={brief.proof} maxLength={500} placeholder="Ex. Une certification, un chiffre vérifié ou un témoignage autorisé. Laissez vide si vous n’en avez pas." onChange={event => change("proof", event.target.value)}/></label>
        <label>Ton souhaité <small>facultatif</small><input value={brief.tone} maxLength={120} placeholder="Ex. Chaleureux, direct et rassurant" onChange={event => change("tone", event.target.value)}/></label>
      </>}
      {stage === 2 && <>
        <p className="eyebrow">ÉTAPE 3 / 3</p><h2>Quelle action doit faire le visiteur ?</h2><p className="sales-help">Le tunnel mène à votre lien de réservation, de contact ou de commande externe. Sillage mesurera les clics vers ce lien.</p>
        <div className="sales-action-presets">{["Prendre rendez-vous", "Demander un devis", "Découvrir l’offre"].map(label => <button type="button" key={label} className={brief.goal_label === label ? "selected" : ""} onClick={() => change("goal_label", label)}>{label}</button>)}</div>
        <label>Texte du bouton final<input value={brief.goal_label} maxLength={100} required minLength={3} onChange={event => change("goal_label", event.target.value)}/></label>
        <label>Adresse de destination<input type="url" value={brief.goal_url} maxLength={2048} required pattern="https://.*" placeholder="https://votre-site.fr/reserver" onChange={event => change("goal_url", event.target.value)}/><small>Le visiteur y arrive après avoir cliqué sur le dernier bouton. Aucun paiement n’est encaissé par Sillage.</small></label>
        <label>Site de référence <small>facultatif</small><input type="url" value={brief.website_url} maxLength={300} placeholder="https://votre-site.fr" onChange={event => change("website_url", event.target.value)}/><small>Luna peut s’en servir comme contexte ; vérifiez toujours les informations reprises.</small></label>
        <div className="sales-summary"><strong>Votre parcours</strong><span>Page de découverte <ArrowRight size={15}/> Page d’offre <ArrowRight size={15}/> {brief.goal_label || "Votre action"} <ExternalLink size={14}/></span></div>
      </>}
      {configured === false && <p className="form-error" role="alert">Luna n’est pas configurée. Ajoutez une clé OpenAI sur le serveur pour générer les pages.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="sales-wizard-actions">{stage > 0 && <button type="button" className="button button-secondary" disabled={busy} onClick={() => setStage(stage - 1)}>Retour</button>}<button className="button button-primary" disabled={!canContinue || busy || (stage === 2 && configured === false)}>{busy ? <><LoaderCircle className="spin" size={17}/>Luna crée vos pages…</> : stage === 2 ? <><Sparkles size={17}/>Créer le tunnel</> : <>Continuer <ArrowRight size={17}/></>}</button></div>
    </form>
  </div>;
}
