"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, FolderOpen, LoaderCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function NewCampaignPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [objective, setObjective] = useState("");
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function create(event: FormEvent) {
    event.preventDefault();
    if (name.trim().length < 3 || busy) return;
    setBusy(true);
    setError("");
    try {
      const campaign = await api<Campaign>("/campaigns", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), client: client.trim(), objective: objective.trim(), starts_on: startsOn || null, ends_on: endsOn || null }),
      });
      router.push(`/campaigns/${campaign.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible");
      setBusy(false);
    }
  }

  return <div className="creation-page">
    <div className="creation-top">
      <Link href="/campaigns" className="back-link"><ArrowLeft size={18}/>Retour aux campagnes</Link>
      <div className="step-indicator">
        <span className="current">1. La campagne</span><i/>
        <span>2. Les formulaires</span><i/>
        <span>3. Publication</span>
      </div>
    </div>

    <section className="luna-stage">
      <div className="luna-symbol"><FolderOpen size={24}/></div>
      <p className="eyebrow">NOUVELLE CAMPAGNE</p>
      <h1>Un dossier pour vos formulaires.</h1>
      <p className="creation-intro">Une campagne regroupe les formulaires d’un même client, d’un même événement ou d’une même opération. Vous ajouterez les formulaires juste après.</p>
      <form onSubmit={create} className="prompt-form creation-basics">
        <label>Nom de la campagne
          <input value={name} maxLength={140} placeholder="Ex. Portes ouvertes d’octobre" onChange={event => setName(event.target.value)} autoFocus/>
        </label>
        <label>Client <small>facultatif</small>
          <input value={client} maxLength={140} placeholder="Ex. Atelier Rivage" onChange={event => setClient(event.target.value)}/>
        </label>
        <label>Objectif <small>facultatif</small>
          <textarea value={objective} maxLength={600} placeholder="Ex. Remplir les créneaux de visite de l’atelier." onChange={event => setObjective(event.target.value)}/>
        </label>
        <div className="period-fields">
          <label>Début <small>facultatif</small><input type="date" value={startsOn} onChange={event => setStartsOn(event.target.value)}/></label>
          <label>Fin <small>facultatif</small><input type="date" value={endsOn} min={startsOn || undefined} onChange={event => setEndsOn(event.target.value)}/></label>
        </div>
        {error && <p className="form-error">{error}</p>}
        <button className="button button-primary button-large" disabled={busy || name.trim().length < 3}>
          {busy ? <><LoaderCircle className="spin" size={19}/>Création…</> : <>Créer la campagne <ArrowRight size={18}/></>}
        </button>
      </form>
      <div className="creation-reassurance"><span><Check size={16}/>Autant de formulaires que nécessaire</span><span><Check size={16}/>Un bilan commun</span><span><Check size={16}/>Modifiable à tout moment</span></div>
    </section>
  </div>;
}
