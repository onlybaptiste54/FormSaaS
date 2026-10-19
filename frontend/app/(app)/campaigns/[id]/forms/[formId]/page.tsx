"use client";

import { FormEvent, use, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowDown, ArrowUp, BarChart3, Check, ChevronRight, Code2, Copy, Eye, FileText, Globe2, Link2, MessageSquareText, Plus, Save, Send, Settings2 } from "lucide-react";
import { LunaFormEditor } from "@/components/luna-form-editor";
import { ResponsesInbox } from "@/components/responses-inbox";
import { useMe } from "@/components/shell";
import { Badge, ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { thankYouTitle } from "@/lib/form-text";
import type { Form, FormTunnel, TunnelPage } from "@/lib/types";

export default function FormDetail({ params }: { params: Promise<{ id: string; formId: string }> }) {
  const { id, formId } = use(params);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [saved, setSaved] = useState(false);
  const [targetPage, setTargetPage] = useState<TunnelPage | null>(null);

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

  async function refreshTargetPage(pageId: string) {
    const tunnel = await api<FormTunnel>(`/forms/${formId}/tunnel`);
    setTargetPage(tunnel.pages.find(page => page.id === pageId) || null);
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
      <button className={tab === "form" ? "active" : ""} onClick={() => { setTargetPage(null); setTab("form"); }}><FileText size={18}/>Formulaire</button>
      <button className={tab === "responses" ? "active" : ""} onClick={() => setTab("responses")}><MessageSquareText size={18}/>Réponses <span>{form.responses}</span></button>
      <button className={tab === "share" ? "active" : ""} onClick={() => setTab("share")}><Globe2 size={18}/>Diffusion</button>
      <button className={tab === "tunnel" ? "active" : ""} onClick={() => setTab("tunnel")}><Settings2 size={18}/>Tunnel</button>
    </nav>
    {tab === "overview" && <Overview form={form} onEdit={() => setTab("form")}/>}
    {tab === "form" && <LunaFormEditor form={form} onFormChange={setForm} targetPage={targetPage} onTargetPageChange={refreshTargetPage}/>}
    {tab === "responses" && <div className="detail-content"><ResponsesInbox formId={form.id}/></div>}
    {tab === "share" && <Share form={form}/>}
    {tab === "tunnel" && <Tunnel
      form={form} onSave={saveThankYou} saved={saved}
      onEditPage={page => { setTargetPage(page); setTab("form"); }}
    />}
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

const pageRoleLabels: Record<TunnelPage["role"], string> = {
  landing: "Page d’accueil", form: "Formulaire", thanks: "Remerciement", step: "Étape", custom: "Page",
};

function TunnelPages({ formId, onEditPage }: { formId: string; onEditPage: (page: TunnelPage) => void }) {
  const [tunnel, setTunnel] = useState<FormTunnel | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [newRole, setNewRole] = useState<"landing" | "form">("landing");
  const [newName, setNewName] = useState("");

  async function reload() {
    setTunnel(await api<FormTunnel>(`/forms/${formId}/tunnel`));
  }

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    void api<FormTunnel>(`/forms/${formId}/tunnel`)
      .then(data => { if (current) setTunnel(data); })
      .catch(err => { if (current) setError(err instanceof Error ? err.message : "Tunnel indisponible"); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [formId]);

  async function change(pageId: string, changes: { next_page_id?: string | null; position?: number }) {
    setBusy(true);
    setError("");
    try {
      await api(`/forms/${formId}/tunnel/pages/${pageId}`, { method: "PATCH", body: JSON.stringify(changes) });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Modification impossible");
    } finally {
      setBusy(false);
    }
  }

  async function addPage(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/forms/${formId}/tunnel/pages`, {
        method: "POST", body: JSON.stringify({ role: newRole, name: newName.trim() || undefined }),
      });
      setNewName("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible");
    } finally {
      setBusy(false);
    }
  }

  const pages = [...(tunnel?.pages || [])].sort((left, right) => left.position - right.position);
  const byId = new Map(pages.map(page => [page.id, page]));

  return <section className="panel tunnel-pages">
    <div className="panel-head"><div><p className="eyebrow">PARCOURS VISITEUR</p><h2>Pages du tunnel</h2></div><span className="tunnel-pages-count">{pages.length} étapes</span></div>
    <p className="tunnel-pages-intro">Organisez les pages et indiquez où mène chaque étape. Les visites et les passages sont comptés sur chaque page.</p>
    {loading && <p className="tunnel-pages-state">Chargement des étapes…</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {!loading && pages.length === 0 && <p className="tunnel-pages-state">Aucune page dans ce tunnel.</p>}
    <ol className="tunnel-page-list">{pages.map((page, index) => {
      const next = page.next_page_id ? byId.get(page.next_page_id) : undefined;
      const abandonment = next && page.visits > 0
        ? `${Math.max(0, Math.min(100, Math.round(100 * (1 - next.visits / page.visits))))} %`
        : "—";
      return <li className="tunnel-page-row" key={page.id}>
        <div className="tunnel-page-identity">
          <span className="tunnel-page-number">{String(index + 1).padStart(2, "0")}</span>
          <div><strong>{pageRoleLabels[page.role]}</strong>{page.id === tunnel?.entry_page_id && <span className="tunnel-entry-tag">Entrée</span>}<small>{page.slug || `Page ${index + 1}`}</small></div>
        </div>
        <div className="tunnel-page-stats">
          <span><strong>{page.visits}</strong><small>Visites</small></span>
          <span><strong>{page.conversions}</strong><small>Passages</small></span>
          <span><strong>{abandonment}</strong><small>Abandon</small></span>
        </div>
        <div className="tunnel-page-controls">
          {page.role !== "thanks" && <label>Étape suivante
            <select value={page.next_page_id || ""} disabled={busy} onChange={event => void change(page.id, { next_page_id: event.target.value || null })}>
              <option value="">Fin du parcours</option>
              {pages.filter(candidate => candidate.id !== page.id).map(candidate =>
                <option value={candidate.id} key={candidate.id}>{pageRoleLabels[candidate.role]} · {candidate.slug}</option>) }
            </select>
          </label>}
          <div className="tunnel-page-order" aria-label={`Ordre de ${pageRoleLabels[page.role]}`}>
            <button type="button" aria-label="Monter cette page" title="Monter" disabled={busy || index === 0 || page.role === "thanks" || pages[index - 1]?.role === "thanks"} onClick={() => void change(page.id, { position: pages[index - 1].position })}><ArrowUp size={16}/></button>
            <button type="button" aria-label="Descendre cette page" title="Descendre" disabled={busy || index === pages.length - 1 || page.role === "thanks" || pages[index + 1]?.role === "thanks"} onClick={() => void change(page.id, { position: pages[index + 1].position })}><ArrowDown size={16}/></button>
          </div>
          {page.id !== formId && page.role !== "thanks" && <button type="button" className="text-link" onClick={() => onEditPage(page)}>Modifier avec Luna</button>}
        </div>
      </li>;
    })}</ol>
    <form className="tunnel-page-add" onSubmit={event => void addPage(event)}>
      <label>Type de page<select value={newRole} onChange={event => setNewRole(event.target.value as "landing" | "form")} disabled={busy}>
        <option value="landing">Page d’accueil</option><option value="form">Formulaire</option>
      </select></label>
      <label>Nom (facultatif)<input value={newName} onChange={event => setNewName(event.target.value)} maxLength={90} placeholder="Ex. Présentation" disabled={busy}/></label>
      <button className="button button-secondary" disabled={busy}><Plus size={16}/>Ajouter une page</button>
    </form>
  </section>;
}

function Tunnel({ form, onSave, saved, onEditPage }: { form: Form; onSave: (data: Record<string, string>) => Promise<void>; saved: boolean; onEditPage: (page: TunnelPage) => void }) {
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

  return <div className="detail-content"><TunnelPages formId={form.id} onEditPage={onEditPage}/><div className="tunnel-grid">
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
