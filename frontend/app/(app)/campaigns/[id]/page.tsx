"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Archive, ArchiveRestore, ArrowLeft, BarChart3, Check, Copy, ExternalLink, FileText, LayoutTemplate, MessageSquareText, Plus, Save, Settings2 } from "lucide-react";
import { FormRenderer, FormStage } from "@/components/form-renderer";
import { ResponsesInbox } from "@/components/responses-inbox";
import { useMe } from "@/components/shell";
import { Badge, EmptyState, ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign, CampaignStats, Form } from "@/lib/types";

const longDate = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" });
const shortDate = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" });
const weekday = new Intl.DateTimeFormat("fr-FR", { weekday: "short" });

export default function CampaignDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [forms, setForms] = useState<Form[] | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("forms");

  const load = () => {
    setError("");
    Promise.all([api<Campaign>(`/campaigns/${id}`), api<Form[]>(`/campaigns/${id}/forms`)])
      .then(([data, list]) => { setCampaign(data); setForms(list); })
      .catch(err => setError(err instanceof Error ? err.message : "Campagne introuvable"));
  };
  useEffect(() => { load(); }, [id]);

  if (error) return <div className="detail-page"><ErrorState message={error} onRetry={load}/></div>;
  if (!campaign || !forms) return <Loading/>;

  const period = campaign.starts_on || campaign.ends_on
    ? `${campaign.starts_on ? shortDate.format(new Date(campaign.starts_on)) : "…"} → ${campaign.ends_on ? shortDate.format(new Date(campaign.ends_on)) : "…"}`
    : "";

  return <div className="detail-page">
    <div className="detail-top">
      <Link href="/campaigns" className="back-link"><ArrowLeft size={18}/>Campagnes</Link>
      <div className="detail-actions">
        <Link href={`/campaigns/${id}/forms/new`} className="button button-primary"><Plus size={18}/>Nouveau formulaire</Link>
      </div>
    </div>
    <header className="campaign-title">
      <div>
        <div className="title-line"><h1>{campaign.name}</h1>{campaign.active > 0 ? <Badge tone="green">{campaign.active} formulaire{campaign.active > 1 ? "s" : ""} en ligne</Badge> : <Badge tone="amber">Aucun formulaire en ligne</Badge>}</div>
        <p>{[campaign.client, period, campaign.objective].filter(Boolean).join(" · ") || "Aucune information complémentaire"}</p>
      </div>
    </header>
    <nav className="detail-tabs">
      <button className={tab === "forms" ? "active" : ""} onClick={() => setTab("forms")}><LayoutTemplate size={18}/>Formulaires <span>{campaign.forms}</span></button>
      <button className={tab === "stats" ? "active" : ""} onClick={() => setTab("stats")}><BarChart3 size={18}/>Statistiques</button>
      <button className={tab === "responses" ? "active" : ""} onClick={() => setTab("responses")}><MessageSquareText size={18}/>Réponses <span>{campaign.responses}</span></button>
      <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}><Settings2 size={18}/>Paramètres</button>
    </nav>
    {tab === "forms" && <Forms campaign={campaign} forms={forms} onReload={load}/>}
    {tab === "stats" && <Stats campaign={campaign}/>}
    {tab === "responses" && <div className="detail-content"><ResponsesInbox campaignId={campaign.id}/></div>}
    {tab === "settings" && <Settings campaign={campaign} onSaved={setCampaign}/>}
  </div>;
}

function Forms({ campaign, forms, onReload }: { campaign: Campaign; forms: Form[]; onReload: () => void }) {
  const me = useMe();
  const company = { name: me?.company.name || "Votre entreprise", logo: me?.company.logo };

  async function duplicate(form: Form) {
    await api(`/forms/${form.id}/duplicate`, { method: "POST" });
    onReload();
  }

  async function setArchived(form: Form, archived: boolean) {
    await api(`/forms/${form.id}`, { method: "PATCH", body: JSON.stringify({ archived }) });
    onReload();
  }

  if (!forms.length) return <div className="detail-content">
    <EmptyState icon={<FileText/>} title="Aucun formulaire dans cette campagne" text="Décrivez ce que vous voulez demander : Luna construit le formulaire, vous l’ajustez ensuite." action={<Link href={`/campaigns/${campaign.id}/forms/new`} className="button button-primary"><Plus size={18}/>Créer le premier formulaire</Link>}/>
  </div>;

  return <div className="detail-content">
    <div className="form-card-grid">
      {forms.map(form => <article className={`panel form-card ${form.archived ? "archived" : ""}`} key={form.id}>
        <Link href={`/campaigns/${campaign.id}/forms/${form.id}`} className="form-card-preview" aria-label={`Ouvrir ${form.name}`}>
          <FormStage design={form.design} className="template-miniature">
            <div className="template-miniature-scale"><FormRenderer form={form} company={company} mode="thumb"/></div>
          </FormStage>
        </Link>
        <div className="form-card-copy">
          <div className="title-line">
            <Link href={`/campaigns/${campaign.id}/forms/${form.id}`}><strong>{form.name}</strong></Link>
            <Badge tone={form.archived ? "neutral" : form.status === "active" ? "green" : "amber"}>{form.archived ? "Archivé" : form.status === "active" ? "En ligne" : "En pause"}</Badge>
          </div>
          <p>{form.responses} réponses · {form.conversion} % de conversion</p>
          <div className="form-card-actions">
            <a className="icon-button" href={`/forms/${form.slug}?preview=1`} target="_blank" title="Prévisualiser" aria-label={`Prévisualiser ${form.name}`}><ExternalLink size={17}/></a>
            <button className="icon-button" onClick={() => void duplicate(form)} title="Dupliquer" aria-label={`Dupliquer ${form.name}`}><Copy size={17}/></button>
            {form.archived
              ? <button className="icon-button" onClick={() => void setArchived(form, false)} title="Restaurer" aria-label={`Restaurer ${form.name}`}><ArchiveRestore size={17}/></button>
              : <button className="icon-button" onClick={() => void setArchived(form, true)} title="Archiver" aria-label={`Archiver ${form.name}`}><Archive size={17}/></button>}
          </div>
        </div>
      </article>)}
    </div>
  </div>;
}

function Stats({ campaign }: { campaign: Campaign }) {
  const [stats, setStats] = useState<CampaignStats | null>(null);
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    api<CampaignStats>(`/campaigns/${campaign.id}/stats`).then(setStats).catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, [campaign.id]);

  if (error) return <div className="detail-content"><ErrorState message={error} onRetry={load}/></div>;
  if (!stats) return <div className="detail-content"><Loading/></div>;

  const max = Math.max(...stats.daily.map(day => day.count), 1);
  const total = stats.sources.reduce((sum, source) => sum + source.count, 0);

  return <div className="detail-content">
    <section className="metric-grid">
      <article className="metric-card"><p>Formulaires</p><strong>{stats.forms}</strong><span>{stats.active} en ligne</span></article>
      <article className="metric-card"><p>Visites</p><strong>{stats.visits}</strong><span>Toutes sources</span></article>
      <article className="metric-card"><p>Réponses</p><strong>{stats.responses}</strong><span>Collectées</span></article>
      <article className="metric-card"><p>Conversion</p><strong>{stats.conversion} %</strong><span>{stats.best ? `Meilleur : ${stats.best.name}` : "Visite → réponse"}</span></article>
    </section>
    <div className="campaign-stats-grid">
      <article className="panel">
        <div className="panel-head"><div><p className="eyebrow">PAR FORMULAIRE</p><h2>Ce que chacun apporte</h2></div></div>
        <div className="breakdown-list">
          {stats.breakdown.map(row => <Link href={`/campaigns/${campaign.id}/forms/${row.id}`} key={row.id}>
            <div><strong>{row.name}</strong><span>{row.visits} visites · {row.conversion} % de conversion</span></div>
            <b>{row.responses}</b>
          </Link>)}
        </div>
      </article>
      <article className="panel">
        <div className="panel-head"><div><p className="eyebrow">ACTIVITÉ</p><h2>7 derniers jours</h2></div></div>
        <div className="bar-chart">{stats.daily.map(day => <div key={day.date}><i style={{ height: `${Math.round(day.count / max * 100)}%` }} title={`${day.count} réponses`}/><span>{weekday.format(new Date(day.date))}</span></div>)}</div>
      </article>
      <article className="panel">
        <div className="panel-head"><div><p className="eyebrow">ACQUISITION</p><h2>Sources</h2></div></div>
        <div className="source-list">
          {!stats.sources.length && <p className="muted">Aucune réponse collectée pour le moment.</p>}
          {stats.sources.map((source, index) => <div className="source-row" key={source.name}>
            <span className={`source-dot dot-${index % 4}`}/>
            <div><div className="source-label"><strong>{source.name}</strong><span>{Math.round(source.count / total * 100)} %</span></div><div className="progress"><i style={{ width: `${Math.round(source.count / total * 100)}%` }}/></div></div>
          </div>)}
        </div>
      </article>
    </div>
  </div>;
}

function Settings({ campaign, onSaved }: { campaign: Campaign; onSaved: (campaign: Campaign) => void }) {
  const router = useRouter();
  const [data, setData] = useState({ name: campaign.name, client: campaign.client, objective: campaign.objective, starts_on: campaign.starts_on || "", ends_on: campaign.ends_on || "" });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setError("");
    try {
      onSaved(await api<Campaign>(`/campaigns/${campaign.id}`, { method: "PATCH", body: JSON.stringify({ ...data, starts_on: data.starts_on || null, ends_on: data.ends_on || null }) }));
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible");
    }
  }

  async function archive() {
    await api(`/campaigns/${campaign.id}`, { method: "PATCH", body: JSON.stringify({ archived: !campaign.archived }) });
    router.push("/campaigns");
  }

  return <div className="detail-content"><div className="detail-grid">
    <article className="panel campaign-settings">
      <p className="eyebrow">LA CAMPAGNE</p>
      <h2>Informations</h2>
      <label>Nom<input value={data.name} maxLength={140} onChange={event => setData({ ...data, name: event.target.value })}/></label>
      <label>Client<input value={data.client} maxLength={140} onChange={event => setData({ ...data, client: event.target.value })}/></label>
      <label>Objectif<textarea value={data.objective} maxLength={600} onChange={event => setData({ ...data, objective: event.target.value })}/></label>
      <div className="period-fields">
        <label>Début<input type="date" value={data.starts_on} onChange={event => setData({ ...data, starts_on: event.target.value })}/></label>
        <label>Fin<input type="date" value={data.ends_on} min={data.starts_on || undefined} onChange={event => setData({ ...data, ends_on: event.target.value })}/></label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="button button-primary" onClick={() => void save()} disabled={data.name.trim().length < 3}>{saved ? <><Check size={17}/>Enregistré</> : <><Save size={17}/>Enregistrer</>}</button>
    </article>
    <article className="panel">
      <p className="eyebrow">SUIVI</p>
      <h2>Repères</h2>
      <dl className="detail-facts">
        <div><dt>Formulaires</dt><dd>{campaign.forms}</dd></div>
        <div><dt>Réponses</dt><dd>{campaign.responses}</dd></div>
        <div><dt>Créée le</dt><dd>{longDate.format(new Date(campaign.created_at))}</dd></div>
        <div><dt>Dernière activité</dt><dd>{longDate.format(new Date(campaign.last_activity))}</dd></div>
      </dl>
      <p className="field-hint">Archiver la campagne retire ses formulaires des statistiques globales et de la page d’accueil. Aucune réponse n’est supprimée, et les liens publics cessent de répondre.</p>
      <button className="button button-secondary" onClick={() => void archive()}>{campaign.archived ? <><ArchiveRestore size={17}/>Restaurer la campagne</> : <><Archive size={17}/>Archiver la campagne</>}</button>
    </article>
  </div></div>;
}
