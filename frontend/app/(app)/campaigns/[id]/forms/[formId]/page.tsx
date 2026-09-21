"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, BarChart3, Check, ChevronRight, Code2, Copy, Eye, FileText, Globe2, Link2, MessageSquareText, Save, Send, Settings2 } from "lucide-react";
import { LunaFormEditor } from "@/components/luna-form-editor";
import { ResponsesInbox } from "@/components/responses-inbox";
import { useMe } from "@/components/shell";
import { Badge, ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { thankYouTitle } from "@/lib/form-text";
import type { Form } from "@/lib/types";

export default function FormDetail({ params }: { params: Promise<{ id: string; formId: string }> }) {
  const { id, formId } = use(params);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [saved, setSaved] = useState(false);

  const load = () => {
    setError("");
    api<Form>(`/forms/${formId}`).then(setForm).catch(err => setError(err instanceof Error ? err.message : "Formulaire introuvable"));
  };
  useEffect(() => {
    load();
    if (new URLSearchParams(window.location.search).get("tab") === "form") setTab("form");
  }, [formId]);

  async function publish() {
    if (!form) return;
    setForm(await api<Form>(`/forms/${formId}`, { method: "PATCH", body: JSON.stringify({ status: form.status === "active" ? "draft" : "active" }) }));
  }

  async function saveThankYou(data: Record<string, string>) {
    setForm(await api<Form>(`/forms/${formId}`, { method: "PATCH", body: JSON.stringify({ thank_you: data }) }));
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  if (error) return <div className="detail-page"><ErrorState message={error} onRetry={load}/></div>;
  if (!form) return <Loading/>;

  return <div className="detail-page">
    <div className="detail-top">
      <nav className="breadcrumb">
        <Link href="/campaigns">Campagnes</Link><ChevronRight size={15}/>
        <Link href={`/campaigns/${id}`}>{form.campaign_name}</Link><ChevronRight size={15}/>
        <span>{form.name}</span>
      </nav>
      <div className="detail-actions">
        <a href={`/forms/${form.slug}?preview=1`} target="_blank" className="button button-secondary"><Eye size={18}/>Prévisualiser</a>
        <button onClick={() => void publish()} className="button button-primary">{form.status === "active" ? "Mettre en pause" : <><Send size={17}/>Publier</>}</button>
      </div>
    </div>
    <header className="campaign-title">
      <div><div className="title-line"><h1>{form.name}</h1><Badge tone={form.status === "active" ? "green" : "amber"}>{form.status === "active" ? "En ligne" : "En pause"}</Badge></div><p>{form.description}</p></div>
    </header>
    <nav className="detail-tabs">
      <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}><BarChart3 size={18}/>Vue d’ensemble</button>
      <button className={tab === "form" ? "active" : ""} onClick={() => setTab("form")}><FileText size={18}/>Formulaire</button>
      <button className={tab === "responses" ? "active" : ""} onClick={() => setTab("responses")}><MessageSquareText size={18}/>Réponses <span>{form.responses}</span></button>
      <button className={tab === "share" ? "active" : ""} onClick={() => setTab("share")}><Globe2 size={18}/>Diffusion</button>
      <button className={tab === "tunnel" ? "active" : ""} onClick={() => setTab("tunnel")}><Settings2 size={18}/>Tunnel</button>
    </nav>
    {tab === "overview" && <Overview form={form} onEdit={() => setTab("form")}/>}
    {tab === "form" && <LunaFormEditor form={form} onFormChange={setForm}/>}
    {tab === "responses" && <div className="detail-content"><ResponsesInbox formId={form.id}/></div>}
    {tab === "share" && <Share form={form}/>}
    {tab === "tunnel" && <Tunnel form={form} onSave={saveThankYou} saved={saved}/>}
  </div>;
}

function Overview({ form, onEdit }: { form: Form; onEdit: () => void }) {
  const date = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" });
  return <div className="detail-content">
    <section className="metric-grid metric-grid-3">
      <article className="metric-card"><p>Visites</p><strong>{form.visits}</strong><span>Depuis la création</span></article>
      <article className="metric-card"><p>Réponses</p><strong>{form.responses}</strong><span>Collectées</span></article>
      <article className="metric-card"><p>Conversion</p><strong>{form.conversion} %</strong><span>Visite → réponse</span></article>
    </section>
    <div className="detail-grid">
      <article className="panel">
        <div className="panel-head"><div><p className="eyebrow">FORMULAIRE</p><h2>{form.fields.length} champs configurés</h2></div><button className="text-link" onClick={onEdit}>Modifier avec Luna</button></div>
        <div className="field-summary">{form.fields.map((field, index) => <div key={field.id}><span>{String(index + 1).padStart(2, "0")}</span><strong>{field.label}</strong><small>{labelType(field.type)}{field.required ? " · requis" : ""}</small></div>)}</div>
      </article>
      <article className="panel health-card">
        <p className="eyebrow">QUALITÉ</p>
        <h2>{form.health.score >= 85 ? "Prêt à convertir" : form.health.score >= 60 ? "Quelques réglages" : "À revoir"}</h2>
        <div className="health-score"><strong>{form.health.score}</strong><span>/100</span></div>
        <ul>{form.health.checks.map(check => <li key={check.label} className={check.ok ? "" : "todo"}>{check.ok ? <Check/> : <AlertCircle/>}<span>{check.ok ? check.label : check.hint}</span></li>)}</ul>
      </article>
      <article className="panel">
        <p className="eyebrow">INFORMATIONS</p>
        <h2>Suivi</h2>
        <dl className="detail-facts">
          <div><dt>Campagne</dt><dd>{form.campaign_name}</dd></div>
          <div><dt>Statut</dt><dd>{form.status === "active" ? "En ligne" : "En pause"}</dd></div>
          <div><dt>Type</dt><dd>{({ contact: "Contact", survey: "Sondage", information: "Information" } as Record<string, string>)[form.kind] || form.kind}</dd></div>
          <div><dt>Créé le</dt><dd>{date.format(new Date(form.created_at))}</dd></div>
          <div><dt>Modifié le</dt><dd>{date.format(new Date(form.updated_at))}</dd></div>
          <div><dt>Adresse</dt><dd className="mono">/forms/{form.slug}</dd></div>
        </dl>
      </article>
    </div>
  </div>;
}

const channels = [
  { key: "Lien direct", hint: "Signature, messagerie, conversation" },
  { key: "QR Code", hint: "Affiche, comptoir, véhicule" },
  { key: "Website", hint: "Bouton ou page de votre site" },
  { key: "Email", hint: "Newsletter et campagnes email" },
  { key: "Réseaux sociaux", hint: "Publication et bio" },
];

function Share({ form }: { form: Form }) {
  const [channel, setChannel] = useState(channels[0].key);
  const [copied, setCopied] = useState("");
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const url = channel === "Lien direct" ? `${origin}/forms/${form.slug}` : `${origin}/forms/${form.slug}?source=${encodeURIComponent(channel)}`;
  const iframe = `<iframe src="${origin}/forms/${form.slug}?source=Website" width="100%" height="720" style="border:0" title="${form.name}"></iframe>`;

  function copy(value: string, key: string) {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    });
  }

  return <div className="detail-content">
    <div className="share-hero">
      <p className="eyebrow">DIFFUSION</p>
      <h2>Partagez votre formulaire partout.</h2>
      <p>Choisissez un canal : il est repris tel quel dans vos statistiques d’acquisition.</p>
      <div className="channel-picker">{channels.map(item => <button key={item.key} className={channel === item.key ? "selected" : ""} onClick={() => setChannel(item.key)}><strong>{item.key}</strong><small>{item.hint}</small></button>)}</div>
      <div className="copy-field"><Link2 size={18}/><span>{url}</span><button onClick={() => copy(url, "url")}>{copied === "url" ? <><Check size={17}/>Copié</> : <><Copy size={17}/>Copier</>}</button></div>
      {form.status !== "active" && <p className="share-warning">Ce formulaire est en pause : le lien l’affiche mais n’accepte pas encore de réponse.</p>}
    </div>
    <article className="panel share-embed">
      <div className="panel-head"><div><p className="eyebrow">INTÉGRATION</p><h2>Sur votre site</h2></div><button className="text-link" onClick={() => copy(iframe, "iframe")}>{copied === "iframe" ? <><Check size={15}/>Copié</> : <><Code2 size={15}/>Copier le code</>}</button></div>
      <pre className="embed-code">{iframe}</pre>
    </article>
  </div>;
}

function Tunnel({ form, onSave, saved }: { form: Form; onSave: (data: Record<string, string>) => Promise<void>; saved: boolean }) {
  const me = useMe();
  const [data, setData] = useState<Record<string, string>>(form.thank_you);
  const [error, setError] = useState("");
  const company = me?.company.name || "Votre entreprise";

  async function save() {
    setError("");
    try {
      await onSave(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible");
    }
  }

  return <div className="detail-content"><div className="tunnel-grid">
    <div className="panel tunnel-config">
      <p className="eyebrow">APRÈS L’ENVOI</p>
      <h2>Page de remerciement</h2>
      <label>Titre<input value={data.title || ""} onChange={event => setData({ ...data, title: event.target.value })}/></label>
      <p className="field-hint">Utilisez <code>{"{prenom}"}</code> pour reprendre le prénom, s’il est demandé dans le formulaire.</p>
      <label>Message<textarea value={data.message || ""} onChange={event => setData({ ...data, message: event.target.value })}/></label>
      <label>Action<select value={data.action || "none"} onChange={event => setData({ ...data, action: event.target.value })}>
        <option value="none">Aucune action</option>
        <option value="cta">Bouton vers une page</option>
        <option value="redirect">Redirection automatique</option>
      </select></label>
      {data.action !== "none" && <>
        <label>Texte du bouton<input value={data.button_label || ""} onChange={event => setData({ ...data, button_label: event.target.value })}/></label>
        <label>URL de destination<input value={data.button_url || ""} onChange={event => setData({ ...data, button_url: event.target.value })} placeholder="https://"/></label>
        {data.action === "redirect" && <p className="field-hint">Le visiteur est redirigé après 3 secondes, avec un lien de secours.</p>}
      </>}
      {error && <p className="form-error">{error}</p>}
      <button className="button button-primary" onClick={() => void save()}>{saved ? <><Check size={17}/>Enregistré</> : <><Save size={17}/>Enregistrer</>}</button>
    </div>
    <div className="thanks-preview">
      <div className="client-monogram">{company.split(" ").map(word => word[0]).join("").slice(0, 2).toUpperCase()}</div>
      <div className="thanks-check"><Check/></div>
      <h2>{thankYouTitle(data.title, { name: "Léa Bernard" })}</h2>
      <p>{data.message}</p>
      {data.action !== "none" && <button className="button button-primary">{data.button_label || "Continuer"}</button>}
      <small>{company} · Mentions légales</small>
    </div>
  </div></div>;
}

function labelType(type: string) {
  return ({ text: "Texte court", email: "Email", tel: "Téléphone", textarea: "Texte long", radio: "Choix unique", select: "Liste", rating: "Note", consent: "Consentement", date: "Date", number: "Nombre" } as Record<string, string>)[type] || type;
}
