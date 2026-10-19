"use client";

import { FormEvent, use, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowDown, ArrowUp, BarChart3, Check, ChevronRight, Code2, Copy, Eye, FileText, Globe2, Link2, MessageSquareText, Plus, Save, Send, Settings2 } from "lucide-react";
import { LunaFormEditor } from "@/components/luna-form-editor";
import { ResponsesInbox } from "@/components/responses-inbox";
import { Badge, ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
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

  async function saveThankYou(pageId: string, data: Record<string, string>): Promise<FormTunnel> {
    const tunnel = await api<FormTunnel>(`/forms/${formId}/tunnel/pages/${pageId}`, { method: "PATCH", body: JSON.stringify({ settings: data }) });
    setForm(await api<Form>(`/forms/${formId}`));
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
    return tunnel;
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

function TunnelPages({ form, onSave, saved, onEditPage }: { form: Form; onSave: (pageId: string, data: Record<string, string>) => Promise<FormTunnel>; saved: boolean; onEditPage: (page: TunnelPage) => void }) {
  const [tunnel, setTunnel] = useState<FormTunnel | null>(null);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newRole, setNewRole] = useState<"landing" | "form">("landing");
  const [newName, setNewName] = useState("");
  const [createMode, setCreateMode] = useState<"template" | "scratch">("scratch");
  const [templatePageId, setTemplatePageId] = useState("");
  const [draftName, setDraftName] = useState("");
  const [detailTab, setDetailTab] = useState<"configuration" | "stats">("configuration");
  const [copied, setCopied] = useState(false);

  async function reload() {
    const data = await api<FormTunnel>("/forms/" + form.id + "/tunnel");
    setTunnel(data);
  }

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    void api<FormTunnel>("/forms/" + form.id + "/tunnel")
      .then(data => {
        if (!current) return;
        setTunnel(data);
        setSelectedPageId(data.entry_page_id || data.pages[0]?.id || "");
      })
      .catch(err => { if (current) setError(err instanceof Error ? err.message : "Tunnel indisponible"); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [form.id]);

  const pages = [...(tunnel?.pages || [])].sort((left, right) => left.position - right.position);
  const selectedPage = pages.find(page => page.id === selectedPageId) || pages[0];
  const availableTemplates = pages.filter(page => page.role === newRole);
  const selectedTemplateId = availableTemplates.some(page => page.id === templatePageId)
    ? templatePageId : availableTemplates[0]?.id || "";

  useEffect(() => {
    setDraftName(selectedPage?.name || "");
    setDetailTab("configuration");
  }, [selectedPage?.id, selectedPage?.name]);

  async function change(pageId: string, changes: { name?: string; next_page_id?: string | null; position?: number }) {
    setBusy(true);
    setError("");
    try {
      await api("/forms/" + form.id + "/tunnel/pages/" + pageId, { method: "PATCH", body: JSON.stringify(changes) });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Modification impossible");
    } finally {
      setBusy(false);
    }
  }

  async function addPage(event: FormEvent) {
    event.preventDefault();
    if (!newName.trim() || (createMode === "template" && !selectedTemplateId)) return;
    setBusy(true);
    setError("");
    try {
      const existingIds = new Set(pages.map(page => page.id));
      const created = await api<FormTunnel>("/forms/" + form.id + "/tunnel/pages", {
        method: "POST",
        body: JSON.stringify({
          role: newRole,
          name: newName.trim(),
          ...(createMode === "template" ? { template_page_id: selectedTemplateId } : {}),
        }),
      });
      const newPage = created.pages.find(page => !existingIds.has(page.id));
      setTunnel(created);
      if (newPage) setSelectedPageId(newPage.id);
      setNewName("");
      setShowCreate(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible");
    } finally {
      setBusy(false);
    }
  }

  async function saveName(event: FormEvent) {
    event.preventDefault();
    if (selectedPage && draftName.trim() && draftName.trim() !== selectedPage.name) {
      await change(selectedPage.id, { name: draftName.trim() });
    }
  }

  async function saveThanks(pageId: string, data: Record<string, string>) {
    setTunnel(await onSave(pageId, data));
  }

  const previewPath = selectedPage ? "/forms/" + form.slug + "?preview=1&page=" + selectedPage.id : "";
  async function copyPreviewPath() {
    if (!previewPath) return;
    try {
      await navigator.clipboard.writeText(previewPath);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setError("Impossible de copier le lien d’aperçu.");
    }
  }

  const nextPage = selectedPage?.next_page_id ? pages.find(page => page.id === selectedPage.next_page_id) : undefined;
  const selectedPosition = selectedPage ? pages.findIndex(page => page.id === selectedPage.id) : -1;
  const hasEarlierForm = pages.slice(0, selectedPosition).some(page => page.role === "form");
  const abandonment = selectedPage && nextPage && selectedPage.visits > 0
    ? Math.max(0, Math.min(100, Math.round(100 * (1 - nextPage.visits / selectedPage.visits)))) + " %"
    : "—";

  return <div className="tunnel-studio">
    <aside className="panel tunnel-step-sidebar">
      <div className="tunnel-step-sidebar-head">
        <div><p className="eyebrow">VOTRE PARCOURS</p><h2>Étapes</h2></div>
        <span>{pages.length}</span>
      </div>
      <p className="tunnel-pages-intro">Les flèches réorganisent le parcours. Vous pouvez aussi choisir la page suivante pour chaque étape.</p>
      {loading && <p className="tunnel-pages-state">Chargement des étapes…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <ol className="tunnel-step-list">
        {pages.map((page, index) => {
          const Icon = page.role === "landing" ? Globe2 : page.role === "thanks" ? Check : FileText;
          return <li key={page.id} className={selectedPage?.id === page.id ? "selected" : ""}>
            <button type="button" className="tunnel-step-select" onClick={() => setSelectedPageId(page.id)} aria-current={selectedPage?.id === page.id ? "step" : undefined}>
              <span className="tunnel-step-icon"><Icon size={17}/></span>
              <span className="tunnel-step-copy"><strong>{page.name}</strong><small>{pageRoleLabels[page.role]}{page.id === tunnel?.entry_page_id ? " · Entrée" : ""}</small></span>
            </button>
            <span className="tunnel-step-number">{String(index + 1).padStart(2, "0")}</span>
            {page.role !== "thanks" && <div className="tunnel-page-order" aria-label={"Ordre de " + page.name}>
              <button type="button" aria-label={"Monter " + page.name} title="Monter" disabled={busy || index === 0 || pages[index - 1]?.role === "thanks"} onClick={() => void change(page.id, { position: pages[index - 1].position })}><ArrowUp size={15}/></button>
              <button type="button" aria-label={"Descendre " + page.name} title="Descendre" disabled={busy || index === pages.length - 1 || pages[index + 1]?.role === "thanks"} onClick={() => void change(page.id, { position: pages[index + 1].position })}><ArrowDown size={15}/></button>
            </div>}
          </li>;
        })}
      </ol>
      <button type="button" className="tunnel-step-add" disabled={busy || pages.length >= 20} onClick={() => {
        setNewRole("landing");
        setNewName("");
        setCreateMode(pages.some(page => page.role === "landing") ? "template" : "scratch");
        setTemplatePageId("");
        setShowCreate(true);
      }}><Plus size={17}/>Ajouter une étape</button>
      <div className="tunnel-fallback">
        <p>PAGE DE FIN</p>
        <button type="button" onClick={() => {
          const thanks = pages.find(page => page.role === "thanks");
          if (thanks) setSelectedPageId(thanks.id);
        }}><span><Check size={16}/></span><span><strong>Page de remerciement</strong><small>Après l’envoi du formulaire</small></span></button>
      </div>
    </aside>

    <section className="panel tunnel-step-detail">
      {!selectedPage ? <p className="tunnel-pages-state">Aucune étape disponible.</p> : <>
        <header className="tunnel-step-detail-head">
          <div><p className="eyebrow">{pageRoleLabels[selectedPage.role].toUpperCase()}</p><h2>{selectedPage.name}</h2><span>Étape {pages.findIndex(page => page.id === selectedPage.id) + 1} sur {pages.length}</span></div>
          <div className="tunnel-step-actions">
            <a className="button button-secondary" href={previewPath} target="_blank" rel="noreferrer"><Eye size={17}/>Aperçu de l’étape</a>
            <button type="button" className="button button-primary" onClick={() => onEditPage(selectedPage)}><FileText size={17}/>Modifier la page</button>
          </div>
        </header>
        <nav className="tunnel-step-tabs">
          <button type="button" className={detailTab === "configuration" ? "active" : ""} onClick={() => setDetailTab("configuration")}><Settings2 size={16}/>Configuration</button>
          <button type="button" className={detailTab === "stats" ? "active" : ""} onClick={() => setDetailTab("stats")}><BarChart3 size={16}/>Statistiques</button>
        </nav>

        {detailTab === "stats" ? <div className="tunnel-step-stats tunnel-step-stats-large">
          <span><strong>{selectedPage.visits}</strong><small>Visites</small></span>
          <span><strong>{selectedPage.conversions}</strong><small>Passages vers la suite</small></span>
          <span><strong>{abandonment}</strong><small>Abandon vers l’étape suivante</small></span>
        </div> : selectedPage.role === "thanks"
          ? <ThankYouSettings page={selectedPage} onSave={saveThanks} saved={saved}/>
          : <div className="tunnel-page-config">
            <form className="tunnel-page-name-form" onSubmit={event => void saveName(event)}>
              <label>Nom de l’étape<input value={draftName} onChange={event => setDraftName(event.target.value)} maxLength={100} disabled={busy || selectedPage.id === form.id}/></label>
              <label>URL d’aperçu<div className="tunnel-preview-path"><input readOnly value={previewPath}/><button type="button" onClick={() => void copyPreviewPath()} aria-label="Copier le lien d’aperçu" title="Copier le lien d’aperçu">{copied ? <Check size={17}/> : <Copy size={17}/>}</button></div></label>
              <button type="submit" className="button button-secondary" disabled={busy || !draftName.trim() || draftName.trim() === selectedPage.name || selectedPage.id === form.id}>Enregistrer le nom</button>
            </form>
            <div className="tunnel-next-page">
              <label>Cette étape mène à
                <select value={selectedPage.next_page_id || ""} disabled={busy} onChange={event => void change(selectedPage.id, { next_page_id: event.target.value || null })}>
                  <option value="">Fin du parcours</option>
                  {pages.filter(page => page.id !== selectedPage.id && (page.role !== "thanks" || selectedPage.role === "form" || hasEarlierForm)).map(page =>
                    <option value={page.id} key={page.id}>{page.name} · {pageRoleLabels[page.role]}</option>)}
                </select>
              </label>
              <p>Choisissez la page affichée après le clic sur « Continuer » ou après l’envoi du formulaire.</p>
            </div>
          </div>}
      </>}
    </section>

    {showCreate && <div className="tunnel-modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) setShowCreate(false); }}>
      <section className="tunnel-create-modal" role="dialog" aria-modal="true" aria-labelledby="tunnel-create-title">
        <header><h2 id="tunnel-create-title">Créer une étape</h2><button type="button" aria-label="Fermer" onClick={() => setShowCreate(false)} disabled={busy}><span>×</span></button></header>
        <form onSubmit={event => void addPage(event)}>
          <label>Nom<input value={newName} onChange={event => setNewName(event.target.value)} maxLength={100} required autoFocus placeholder="Ex. Présentation de l’offre"/></label>
          <label>Type de page<select value={newRole} onChange={event => {
            const role = event.target.value as "landing" | "form";
            setNewRole(role);
            setTemplatePageId("");
            setCreateMode(pages.some(page => page.role === role) ? "template" : "scratch");
          }} disabled={busy}>
            <option value="landing">Page de présentation</option><option value="form">Page de collecte</option>
          </select></label>
          <fieldset className="tunnel-create-mode"><legend>Contenu de départ</legend>
            <label><input type="radio" name="createMode" checked={createMode === "template"} disabled={!availableTemplates.length || busy} onChange={() => setCreateMode("template")}/>Choisir un modèle</label>
            <label><input type="radio" name="createMode" checked={createMode === "scratch"} disabled={busy} onChange={() => setCreateMode("scratch")}/>Partir de zéro</label>
          </fieldset>
          {createMode === "template" && (availableTemplates.length
            ? <label>Modèle<select value={selectedTemplateId} onChange={event => setTemplatePageId(event.target.value)} disabled={busy}>
              {availableTemplates.map(page => <option value={page.id} key={page.id}>{page.name}</option>)}
            </select></label>
            : <p className="field-hint">Ajoutez d’abord une page de ce type pour la réutiliser comme modèle.</p>)}
          {error && <p className="form-error" role="alert">{error}</p>}
          <footer><button type="button" className="button button-secondary" onClick={() => setShowCreate(false)} disabled={busy}>Annuler</button><button type="submit" className="button button-primary" disabled={busy || !newName.trim() || (createMode === "template" && !selectedTemplateId)}>{busy ? "Création…" : "Créer l’étape"}</button></footer>
        </form>
      </section>
    </div>}
  </div>;
}

function ThankYouSettings({ page, onSave, saved }: { page: TunnelPage; onSave: (pageId: string, data: Record<string, string>) => Promise<void>; saved: boolean }) {
  const [data, setData] = useState<Record<string, string>>(page.settings || {});
  const [error, setError] = useState("");

  useEffect(() => setData(page.settings || {}), [page.id, page.settings]);

  async function save() {
    setError("");
    try {
      await onSave(page.id, data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible");
    }
  }

  return <div className="tunnel-config tunnel-thanks-config">
    <p className="eyebrow">RÉGLAGES DE LA PAGE</p>
    <h3>{page.name}</h3>
    <label>Titre<input value={data.title || ""} onChange={event => setData({ ...data, title: event.target.value })}/></label>
    <p className="field-hint">Utilisez <code>{"{prenom}"}</code> pour reprendre le prénom, s’il est demandé dans le formulaire.</p>
    <label>Message<textarea value={data.message || ""} onChange={event => setData({ ...data, message: event.target.value })}/></label>
    <label>Action<select value={data.action || "none"} onChange={event => setData({ ...data, action: event.target.value })}>
      <option value="none">Aucune action</option><option value="cta">Bouton vers une page</option><option value="redirect">Redirection automatique</option>
    </select></label>
    {data.action !== "none" && <>
      <label>Texte du bouton<input value={data.button_label || ""} onChange={event => setData({ ...data, button_label: event.target.value })}/></label>
      <label>URL de destination<input value={data.button_url || ""} onChange={event => setData({ ...data, button_url: event.target.value })} placeholder="https://"/></label>
      {data.action === "redirect" && <p className="field-hint">Le visiteur est redirigé après 3 secondes, avec un lien de secours.</p>}
    </>}
    {error && <p className="form-error">{error}</p>}
    <button className="button button-primary" onClick={() => void save()}>{saved ? <><Check size={17}/>Enregistré</> : <><Save size={17}/>Enregistrer</>}</button>
  </div>;
}

function Tunnel({ form, onSave, saved, onEditPage }: { form: Form; onSave: (pageId: string, data: Record<string, string>) => Promise<FormTunnel>; saved: boolean; onEditPage: (page: TunnelPage) => void }) {
  return <div className="detail-content">
    <TunnelPages form={form} onSave={onSave} saved={saved} onEditPage={onEditPage}/>
  </div>;
}

function labelType(type: string) {
  return ({ text: "Texte court", email: "Email", tel: "Téléphone", textarea: "Texte long", radio: "Choix unique", select: "Liste", rating: "Note", consent: "Consentement", date: "Date", number: "Nombre" } as Record<string, string>)[type] || type;
}
