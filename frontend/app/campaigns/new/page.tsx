"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, LoaderCircle, MessageCircle, Sparkles } from "lucide-react";
import Link from "next/link";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

const suggestions = ["Un formulaire de contact pour mon activité", "Un sondage de satisfaction après une visite", "Une inscription pour mon prochain événement"];
export default function NewCampaignPage() {
  const router = useRouter(); const [prompt, setPrompt] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [luna, setLuna] = useState<{configured:boolean;provider:string;model:string|null}|null>(null);
  useEffect(() => { api<{configured:boolean;provider:string;model:string|null}>("/luna/status").then(setLuna).catch(() => undefined); }, []);
  async function create(e: FormEvent) { e.preventDefault(); if (prompt.trim().length < 10) return; setBusy(true); setError(""); try { const c = await api<Campaign>("/campaigns", { method: "POST", body: JSON.stringify({ prompt }) }); router.push(`/campaigns/${c.id}`); } catch (err) { setError(err instanceof Error ? err.message : "Création impossible"); setBusy(false); } }
  return <Shell><div className="creation-page"><div className="creation-top"><Link href="/campaigns" className="back-link"><ArrowLeft size={18}/>Retour aux campagnes</Link><div className="step-indicator"><span className="current">1</span><i/><span>2</span><i/><span>3</span></div></div><section className="luna-stage"><div className="luna-symbol"><Sparkles size={24}/></div><p className="eyebrow">LUNA · CRÉATION ASSISTÉE</p>{luna && <div className={`luna-status ${luna.configured ? "connected" : ""}`}><i/>{luna.configured ? `OpenAI connecté · ${luna.model}` : "Mode local · ajoutez votre clé OpenAI"}</div>}<h1>Que souhaitez-vous créer&nbsp;?</h1><p className="creation-intro">Décrivez simplement votre besoin. Je m’occupe des champs, du texte et de la conformité.</p><form onSubmit={create} className="prompt-form"><div className="prompt-box"><MessageCircle size={20}/><textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Ex. Je veux un formulaire de contact pour mon entreprise de plomberie. J’aimerais connaître le type d’intervention et son niveau d’urgence…" autoFocus/><span>{prompt.length}/1200</span></div>{error && <p className="form-error">{error}</p>}<button className="button button-primary button-large" disabled={busy || prompt.trim().length < 10}>{busy ? <><LoaderCircle className="spin" size={19}/>Luna prépare votre campagne…</> : <>Créer ma campagne <ArrowRight size={18}/></>}</button></form><div className="suggestions"><span>Ou partez d’une idée</span>{suggestions.map(s => <button key={s} onClick={() => setPrompt(s)}>{s}</button>)}</div><div className="creation-reassurance"><span><Check size={16}/>5 à 6 champs maximum</span><span><Check size={16}/>Opt-in RGPD natif</span><span><Check size={16}/>Adapté à votre identité</span></div></section></div></Shell>;
}
