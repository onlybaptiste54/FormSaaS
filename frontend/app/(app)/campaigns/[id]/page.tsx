"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, BarChart3, Check, Code2, Copy, Download, Eye, FileText, Globe2, Link2, MessageSquareText, Save, Send, Settings2, X } from "lucide-react";
import { LunaFormEditor } from "@/components/luna-form-editor";
import { useMe } from "@/components/shell";
import { Badge, ErrorState, Loading } from "@/components/ui";
import { API_URL, api } from "@/lib/api";
import { thankYouTitle } from "@/lib/form-text";
import type { Campaign } from "@/lib/types";

export default function CampaignDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [saved, setSaved] = useState(false);

  const load = () => {
    setError("");
    api<Campaign>(`/campaigns/${id}`).then(setCampaign).catch(err => setError(err instanceof Error ? err.message : "Campagne introuvable"));
  };
  useEffect(() => {
    load();
    if (new URLSearchParams(window.location.search).get("tab") === "form") setTab("form");
  }, [id]);

  async function publish() {
    if (!campaign) return;
    const updated = await api<Campaign>(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify({ status: campaign.status === "active" ? "draft" : "active" }) });
    setCampaign(updated);
  }

  async function saveThankYou(data: Record<string, string>) {
    const updated = await api<Campaign>(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify({ thank_you: data }) });
    setCampaign(updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  if (error) return <div className="detail-page"><ErrorState message={error} onRetry={load}/></div>;
  if (!campaign) return <Loading/>;

  return <div className="detail-page">
    <div className="detail-top">
      <Link href="/campaigns" className="back-link"><ArrowLeft size={18}/>Campagnes</Link>
      <div className="detail-actions">
        <a href={`/forms/${campaign.slug}?preview=1`} target="_blank" className="button button-secondary"><Eye size={18}/>Prévisualiser</a>
        <button onClick={() => void publish()} className="button button-primary">{campaign.status === "active" ? "Mettre en pause" : <><Send size={17}/>Publier</>}</button>
      </div>
    </div>
    <header className="campaign-title">
      <div><div className="title-line"><h1>{campaign.name}</h1><Badge tone={campaign.status === "active" ? "green" : "amber"}>{campaign.status === "active" ? "Active" : "Brouillon"}</Badge></div><p>{campaign.description}</p></div>
    </header>
    <nav className="detail-tabs">
      <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}><BarChart3 size={18}/>Vue d’ensemble</button>
      <button className={tab === "form" ? "active" : ""} onClick={() => setTab("form")}><FileText size={18}/>Formulaire</button>
      <button className={tab === "responses" ? "active" : ""} onClick={() => setTab("responses")}><MessageSquareText size={18}/>Réponses <span>{campaign.responses}</span></button>
      <button className={tab === "share" ? "active" : ""} onClick={() => setTab("share")}><Globe2 size={18}/>Diffusion</button>
      <button className={tab === "tunnel" ? "active" : ""} onClick={() => setTab("tunnel")}><Settings2 size={18}/>Tunnel</button>
    </nav>
    {tab === "overview" && <Overview campaign={campaign} onEdit={() => setTab("form")}/>}
    {tab === "form" && <LunaFormEditor campaign={campaign} onCampaignChange={setCampaign}/>}
    {tab === "responses" && <Responses campaign={campaign}/>}
    {tab === "share" && <Share campaign={campaign}/>}
    {tab === "tunnel" && <Tunnel campaign={campaign} onSave={saveThankYou} saved={saved}/>}
  </div>;
}

function Overview({ campaign, onEdit }: { campaign: Campaign; onEdit: () => void }) {
  const date = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" });
  return <div className="detail-content">
    <section className="metric-grid metric-grid-3">
      <article className="metric-card"><p>Visites</p><strong>{campaign.visits}</strong><span>Depuis la création</span></article>
      <article className="metric-card"><p>Réponses</p><strong>{campaign.responses}</strong><span>Collectées</span></article>
      <article className="metric-card"><p>Conversion</p><strong>{campaign.conversion} %</strong><span>Visite → réponse</span></article>
    </section>
    <div className="detail-grid">
      <article className="panel">
        <div className="panel-head"><div><p className="eyebrow">FORMULAIRE</p><h2>{campaign.fields.length} champs configurés</h2></div><button className="text-link" onClick={onEdit}>Modifier avec Luna</button></div>
        <div className="field-summary">{campaign.fields.map((field, index) => <div key={field.id}><span>{String(index + 1).padStart(2, "0")}</span><strong>{field.label}</strong><small>{labelType(field.type)}{field.required ? " · requis" : ""}</small></div>)}</div>
      </article>
      <article className="panel">
        <p className="eyebrow">INFORMATIONS</p>
        <h2>Suivi</h2>
        <dl className="detail-facts">
          <div><dt>Statut</dt><dd>{campaign.status === "active" ? "Publiée" : "Brouillon"}</dd></div>
          <div><dt>Type</dt><dd>{({ contact: "Contact", survey: "Sondage", information: "Information" } as Record<string, string>)[campaign.kind] || campaign.kind}</dd></div>
          <div><dt>Créée le</dt><dd>{date.format(new Date(campaign.created_at))}</dd></div>
          <div><dt>Modifiée le</dt><dd>{date.format(new Date(campaign.updated_at))}</dd></div>
          <div><dt>Adresse</dt><dd className="mono">/forms/{campaign.slug}</dd></div>
        </dl>
      </article>
    </div>
  </div>;
}

function Responses({ campaign }: { campaign: Campaign }) {
  type Row = { id: string; answers: Record<string, string | number>; source: string; consent: boolean; created_at: string };
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    api<Row[]>(`/campaigns/${campaign.id}/responses`).then(setRows).catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, [campaign.id]);

  async function exportCsv() {
    const token = localStorage.getItem("sillage_token");
    try {
      const response = await fetch(`${API_URL}/campaigns/${campaign.id}/export.csv`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error("Export impossible");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${campaign.slug}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export impossible");
    }
  }

  return <div className="detail-content">
    <div className="response-tools">
      <div><p className="eyebrow">DONNÉES</p><h2>{campaign.responses} réponses</h2></div>
      <button className="button button-secondary" onClick={() => void exportCsv()}><Download size={17}/>Exporter CSV</button>
    </div>
    {error ? <ErrorState message={error} onRetry={load}/> : rows === null ? <Loading/> : <div className="responses-table panel">
      <div className="response-table-head"><span>Contact</span><span>Source</span><span>Consentement</span><span>Reçue le</span></div>
      {rows.map(row => <div className="response-table-row" key={row.id}>
        <div><strong>{row.answers.name || "Réponse anonyme"}</strong><span>{row.answers.email || row.answers.comment || "—"}</span></div>
        <Badge>{row.source}</Badge>
        <span className={row.consent ? "consent-ok" : "consent-ko"}>{row.consent ? <><Check size={15}/>Recueilli</> : <><X size={15}/>Non</>}</span>
        <span>{new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(row.created_at))}</span>
      </div>)}
    </div>}
  </div>;
}

const channels = [
  { key: "Lien direct", hint: "Signature, messagerie, conversation" },
  { key: "QR Code", hint: "Affiche, comptoir, véhicule" },
  { key: "Website", hint: "Bouton ou page de votre site" },
  { key: "Email", hint: "Newsletter et campagnes email" },
  { key: "Réseaux sociaux", hint: "Publication et bio" },
];

function Share({ campaign }: { campaign: Campaign }) {
  const [channel, setChannel] = useState(channels[0].key);
  const [copied, setCopied] = useState("");
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const url = channel === "Lien direct" ? `${origin}/forms/${campaign.slug}` : `${origin}/forms/${campaign.slug}?source=${encodeURIComponent(channel)}`;
  const iframe = `<iframe src="${origin}/forms/${campaign.slug}?source=Website" width="100%" height="720" style="border:0" title="${campaign.name}"></iframe>`;

  function copy(value: string, key: string) {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    });
  }

  return <div className="detail-content">
    <div className="share-hero">
      <p className="eyebrow">DIFFUSION</p>
      <h2>Partagez votre campagne partout.</h2>
      <p>Choisissez un canal : il est repris tel quel dans vos statistiques d’acquisition.</p>
      <div className="channel-picker">{channels.map(item => <button key={item.key} className={channel === item.key ? "selected" : ""} onClick={() => setChannel(item.key)}><strong>{item.key}</strong><small>{item.hint}</small></button>)}</div>
      <div className="copy-field"><Link2 size={18}/><span>{url}</span><button onClick={() => copy(url, "url")}>{copied === "url" ? <><Check size={17}/>Copié</> : <><Copy size={17}/>Copier</>}</button></div>
      {campaign.status !== "active" && <p className="share-warning">Cette campagne est en brouillon : le lien affiche le formulaire mais n’accepte pas encore de réponse.</p>}
    </div>
    <article className="panel share-embed">
      <div className="panel-head"><div><p className="eyebrow">INTÉGRATION</p><h2>Sur votre site</h2></div><button className="text-link" onClick={() => copy(iframe, "iframe")}>{copied === "iframe" ? <><Check size={15}/>Copié</> : <><Code2 size={15}/>Copier le code</>}</button></div>
      <pre className="embed-code">{iframe}</pre>
    </article>
  </div>;
}

function Tunnel({ campaign, onSave, saved }: { campaign: Campaign; onSave: (data: Record<string, string>) => Promise<void>; saved: boolean }) {
  const me = useMe();
  const [data, setData] = useState<Record<string, string>>(campaign.thank_you);
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
