"use client";

import { FormEvent, use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, BarChart3, Check, Download, ExternalLink, Eye, LoaderCircle, Pause, Send, Sparkles, Undo2 } from "lucide-react";
import { PageFrame } from "@/components/page-frame";
import { ErrorState, Loading } from "@/components/ui";
import { API_URL, api, getToken } from "@/lib/api";
import type { SalesPage, SalesStats, SalesTunnel } from "@/lib/types";

type Version = { id: string; created_at: string };

export default function SalesFunnelDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [tunnel, setTunnel] = useState<SalesTunnel | null>(null);
  const [stats, setStats] = useState<SalesStats | null>(null);
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [versions, setVersions] = useState<Version[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [tab, setTab] = useState<"pages" | "stats">("pages");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [instruction, setInstruction] = useState("");
  const [destination, setDestination] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() { setError(""); void api<SalesTunnel>(`/sales-funnels/${id}`).then(result => { setTunnel(result); setDestination(result.goal_url); setSelectedId(current => current || result.entry_page_id); }).catch(reason => setError(reason instanceof Error ? reason.message : "Tunnel introuvable")); }
  useEffect(load, [id]);
  useEffect(() => { if (tab === "stats") { setStats(null); void api<SalesStats>(`/sales-funnels/${id}/stats?days=${days}`).then(setStats).catch(reason => setError(reason instanceof Error ? reason.message : "Statistiques indisponibles")); } }, [id, tab, days]);
  useEffect(() => { if (selectedId) void api<Version[]>(`/sales-funnels/${id}/pages/${selectedId}/versions`).then(setVersions).catch(() => setVersions([])); }, [id, selectedId, tunnel?.status]);

  const page = tunnel?.pages.find(item => item.id === selectedId) || tunnel?.pages[0];
  const hasDrafts = tunnel?.pages.some(item => item.has_draft);

  async function refine(event: FormEvent) {
    event.preventDefault();
    if (!page || instruction.trim().length < 3 || busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api<{ message: string; changed: boolean; tunnel: SalesTunnel }>(`/sales-funnels/${id}/pages/${page.id}/refine`, { method: "POST", body: JSON.stringify({ instruction: instruction.trim() }) });
      setTunnel(result.tunnel); setMessage(result.message); setInstruction("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Luna n’a pas pu modifier la page."); }
    finally { setBusy(false); }
  }

  async function changePublication() {
    if (!tunnel || busy) return;
    setBusy(true); setError("");
    try {
      const action = tunnel.status === "active" && !hasDrafts ? "pause" : "publish";
      const result = await api<SalesTunnel>(`/sales-funnels/${id}/${action}`, { method: "POST" });
      setTunnel(result); setMessage(action === "publish" ? "Le tunnel est en ligne." : "Le tunnel est en pause.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Publication impossible."); }
    finally { setBusy(false); }
  }

  async function saveDestination(event: FormEvent) {
    event.preventDefault();
    if (!tunnel || busy || destination.trim() === tunnel.goal_url) return;
    setBusy(true); setError("");
    try {
      setTunnel(await api<SalesTunnel>(`/sales-funnels/${id}/destination`, { method: "PATCH", body: JSON.stringify({ goal_url: destination.trim() }) }));
      setMessage("Le lien du bouton final a été mis à jour.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Lien invalide."); }
    finally { setBusy(false); }
  }

  async function restore(versionId: string) {
    if (!page || busy) return;
    setBusy(true); setError("");
    try { setTunnel(await api<SalesTunnel>(`/sales-funnels/${id}/pages/${page.id}/versions/${versionId}/restore`, { method: "POST" })); setMessage("Cette version est prête en brouillon. Publiez-la pour la mettre en ligne."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Restauration impossible."); }
    finally { setBusy(false); }
  }

  async function download() {
    if (!tunnel || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${API_URL}/sales-funnels/${id}/export.zip`, { headers: { Authorization: `Bearer ${getToken() || ""}` } });
      if (!response.ok) throw new Error("Export indisponible.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = `${tunnel.slug}.zip`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Export impossible."); }
    finally { setBusy(false); }
  }

  if (error && !tunnel) return <div className="page-wrap"><ErrorState message={error} onRetry={load}/></div>;
  if (!tunnel) return <Loading/>;

  return <div className="page-wrap sales-detail">
    <Link href="/funnels" className="back-link"><ArrowLeft size={17}/>Tunnels de vente</Link>
    <header className="sales-detail-header"><div><p className="eyebrow">TUNNEL DE VENTE</p><h1>{tunnel.name}</h1><p>{tunnel.brief.offer}</p></div><div className="sales-detail-actions"><span className={tunnel.status === "active" ? "badge badge-green" : "badge badge-amber"}>{tunnel.status === "active" ? "En ligne" : "Brouillon"}</span>{tunnel.status === "active" && <><a className="button button-secondary" href={`/t/${tunnel.slug}`} target="_blank" rel="noreferrer"><ExternalLink size={16}/>Voir le tunnel</a><button className="button button-secondary" onClick={() => void download()} disabled={busy}><Download size={16}/>Exporter</button></>}<button className="button button-primary" onClick={() => void changePublication()} disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : tunnel.status === "active" && !hasDrafts ? <Pause size={17}/> : <Send size={17}/>} {tunnel.status === "active" && !hasDrafts ? "Mettre en pause" : hasDrafts ? "Publier les changements" : "Publier"}</button></div></header>
    <nav className="sales-detail-tabs"><button className={tab === "pages" ? "active" : ""} onClick={() => setTab("pages")}><Eye size={17}/>Pages et édition</button><button className={tab === "stats" ? "active" : ""} onClick={() => setTab("stats")}><BarChart3 size={17}/>Statistiques</button></nav>
    {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="sales-feedback" role="status">{message}</p>}
    {tab === "pages" && <div className="sales-studio"><aside className="panel sales-step-panel"><h2>Votre parcours</h2><p>Vérifiez chaque page avant de publier.</p>{tunnel.pages.map((item, index) => <button key={item.id} className={page?.id === item.id ? "selected" : ""} onClick={() => { setSelectedId(item.id); setMessage(""); }}><b>{index + 1}</b><span><strong>{item.name}</strong><small>{item.role === "landing" ? "Présenter le besoin" : "Convaincre et orienter"}{item.has_draft ? " · Brouillon à publier" : ""}</small></span><ArrowRight size={15}/></button>)}<div className="sales-step-goal"><Check size={17}/><span><strong>{tunnel.goal_label}</strong><small>Lien externe mesuré</small></span></div><div className="sales-checklist"><strong>Avant la mise en ligne</strong><span><Check size={14}/> Relisez les prix et les affirmations</span><span><Check size={14}/> Testez le bouton final</span><span><Check size={14}/> Vérifiez l’affichage mobile</span></div></aside>
      <section className="sales-preview-panel"><div className="sales-preview-head"><div><h2>{page?.name}</h2><small>{page?.has_draft ? "Aperçu du brouillon" : "Aperçu de la version publiée"}</small></div><div className="sales-preview-tools"><button className={device === "desktop" ? "selected" : ""} onClick={() => setDevice("desktop")}>Ordinateur</button><button className={device === "mobile" ? "selected" : ""} onClick={() => setDevice("mobile")}>Mobile</button><span>{page?.visits || 0} visites</span></div></div>{page && <div className={`sales-device sales-device-${device}`}><PageFrame html={page.html} title={`Aperçu de ${page.name}`} mode="edit"/></div>}</section>
      <aside className="panel sales-ai-panel"><div className="sales-ai-head"><Sparkles size={20}/><h2>Retoucher avec Luna</h2></div><p>Décrivez un changement précis : « agrandis le titre », « rends l’offre plus claire », « utilise une couleur plus vive ».</p><form onSubmit={event => void refine(event)}><textarea value={instruction} maxLength={800} placeholder="Que souhaitez-vous changer sur cette page ?" onChange={event => setInstruction(event.target.value)} disabled={busy}/><button className="button button-primary" disabled={busy || instruction.trim().length < 3}>{busy ? <LoaderCircle className="spin" size={16}/> : <Sparkles size={16}/>} {busy ? "Luna travaille…" : "Appliquer"}</button></form>{page?.has_draft && <button className="sales-discard" disabled={busy} onClick={async () => { setTunnel(await api<SalesTunnel>(`/sales-funnels/${id}/pages/${page.id}/discard`, { method: "POST" })); setMessage("Brouillon abandonné."); }}>Abandonner les retouches</button>}{versions.length > 0 && <div className="sales-versions"><strong>Versions précédentes</strong>{versions.slice(0, 5).map(version => <button key={version.id} disabled={busy} onClick={() => void restore(version.id)}><Undo2 size={14}/>{new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(version.created_at))}</button>)}</div>}</aside>
    </div>}
    {tab === "pages" && <form className="panel sales-destination-form" onSubmit={event => void saveDestination(event)}><div><h2>Destination du bouton final</h2><p>{tunnel.goal_label} · Le clic est mesuré dans Sillage.</p></div><label>Adresse HTTPS<input type="url" required pattern="https://.*" maxLength={2048} value={destination} onChange={event => setDestination(event.target.value)}/></label><button className="button button-secondary" disabled={busy || destination.trim() === tunnel.goal_url}>Enregistrer le lien</button></form>}
    {tab === "stats" && <div className="sales-stats">
      <div className="sales-period">Période : {[7, 30, 90].map(value => <button key={value} className={days === value ? "selected" : ""} onClick={() => setDays(value as 7 | 30 | 90)}>{value} jours</button>)}</div>
      {!stats ? <Loading/> : <>
        <section className="metric-grid metric-grid-3"><article className="metric-card"><p>Entrées dans le tunnel</p><strong>{stats.visits}</strong><span>Parcours distincts</span></article><article className="metric-card"><p>Clics vers l’action finale</p><strong>{stats.goals}</strong><span>{tunnel.goal_label}</span></article><article className="metric-card"><p>Taux de passage</p><strong>{stats.conversion} %</strong><span>Entrée → clic final</span></article></section>
        <article className="panel sales-trend"><h2>Activité du tunnel</h2><div className="sales-trend-bars">{stats.daily.map(day => { const max = Math.max(...stats.daily.map(item => item.visits), 1); return <div key={day.date} title={`${day.date} · ${day.visits} entrées · ${day.goals} clics finaux`}><span style={{ height: `${Math.max(3, day.visits / max * 100)}%` }}/><i style={{ height: `${Math.max(3, day.goals / max * 100)}%` }}/></div>; })}</div><p>Vert : entrées · Orange : clics finaux</p></article>
        <div className="sales-stats-grid"><article className="panel"><h2>Passage par étape</h2>{stats.pages.map((item, index) => <div className="sales-stat-row" key={item.id}><span>{index + 1}. {item.name}</span><strong>{item.visits} vues</strong><small>{item.continuation === null ? `${item.actions} clics finaux` : `${item.continuation} % poursuivent`}</small></div>)}</article><article className="panel"><h2>Sources de visite</h2>{stats.sources.length ? stats.sources.map(item => <div className="sales-stat-row" key={item.source}><span>{item.source}</span><strong>{item.visits} entrées</strong><small>{item.goals} clics finaux</small></div>) : <p className="muted">Les sources apparaîtront après les premières visites.</p>}</article></div>
        <p className="sales-stats-note">Le clic final indique une intention. Il ne confirme ni une réservation ni une vente sur le site de destination.</p>
      </>}
    </div>}
  </div>;
}
