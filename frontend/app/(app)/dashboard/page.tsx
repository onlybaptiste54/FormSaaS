"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, FileCheck2, FileText, FolderOpen, MousePointerClick, Plus, Waypoints } from "lucide-react";
import { PageHeader, useMe } from "@/components/shell";
import { ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign, SalesOverview, SalesTunnel, Stats } from "@/lib/types";

const day = new Intl.DateTimeFormat("fr-FR", { weekday: "short" });
const today = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });

export default function Dashboard() {
  const me = useMe();
  const [stats, setStats] = useState<Stats | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [funnels, setFunnels] = useState<SalesTunnel[]>([]);
  const [sales, setSales] = useState<SalesOverview | null>(null);
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    Promise.all([api<Stats>("/stats"), api<Campaign[]>("/campaigns"), api<SalesTunnel[]>("/sales-funnels"), api<SalesOverview>("/sales-funnels/overview")])
      .then(([s, c, f, overview]) => { setStats(s); setCampaigns(c); setFunnels(f); setSales(overview); })
      .catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, []);
  const firstName = me?.full_name.split(" ")[0];
  return <div className="page-wrap dashboard-page"><PageHeader eyebrow={today.format(new Date()).toUpperCase()} title={firstName ? `Bonjour ${firstName}.` : "Bonjour."} description="Suivez vos tunnels et les actions de vos visiteurs." actions={<Link href="/funnels/new" className="button button-primary"><Plus size={18} />Créer un tunnel</Link>} />
    {error ? <ErrorState message={error} onRetry={load} /> : !stats || !sales ? <Loading /> : <>
      <section className="panel sales-dashboard-panel"><div className="panel-head"><div><p className="eyebrow">TUNNELS DE VENTE</p><h2>Vos parcours</h2></div><Link href="/funnels" className="text-link">Tout voir <ArrowRight size={16}/></Link></div>{funnels.length ? <div className="sales-dashboard-list">{funnels.slice(0, 3).map(funnel => <Link href={`/funnels/${funnel.id}`} key={funnel.id}><Waypoints size={19}/><span><strong>{funnel.name}</strong><small>{funnel.status === "active" ? "En ligne" : "Brouillon"} · {funnel.goal_label}</small></span><ArrowRight size={16}/></Link>)}</div> : <p className="muted">Aucun tunnel pour le moment. Commencez par décrire votre offre à Luna.</p>}</section>
      <p className="eyebrow sales-legacy-heading">PERFORMANCE DES TUNNELS · 30 DERNIERS JOURS</p>
      <section className="metric-grid">
        <Metric icon={<Waypoints/>} label="Tunnels en ligne" value={sales.active.toString()} note={`${sales.drafts} brouillon${sales.drafts > 1 ? "s" : ""}`} />
        <Metric icon={<MousePointerClick/>} label="Entrées" value={sales.visits.toLocaleString("fr-FR")} note="Parcours distincts" />
        <Metric icon={<ArrowRight/>} label="Clics finaux" value={sales.goals.toLocaleString("fr-FR")} note="Vers vos liens externes" />
        <Metric icon={<FileCheck2/>} label="Taux de passage" value={`${sales.conversion} %`} note="Entrée → clic final" />
      </section>
      <p className="eyebrow sales-legacy-heading">FORMULAIRES ET RÉPONSES</p>
      <section className="metric-grid">
        <Metric icon={<FolderOpen />} label="Campagnes" value={stats.campaigns.toString()} note={`${stats.forms} formulaire${stats.forms > 1 ? "s" : ""}`} />
        <Metric icon={<FileText />} label="Formulaires en ligne" value={stats.active.toString()} note={stats.drafts ? `${stats.drafts} en pause` : "Tout est publié"} />
        <Metric icon={<FileCheck2 />} label="Réponses collectées" value={stats.responses.toLocaleString("fr-FR")} note={`+${stats.week_responses} cette semaine`} positive />
        <Metric icon={<MousePointerClick />} label="Taux de conversion" value={`${stats.conversion} %`} note="Toutes campagnes" />
      </section>
      <section className="dashboard-grid">
        <article className="panel chart-panel"><div className="panel-head"><div><p className="eyebrow">ACTIVITÉ</p><h2>Réponses sur 7 jours</h2></div><span className="chart-total">{stats.week_responses} <small>réponses</small></span></div><LineChart data={stats.daily} /></article>
        <article className="panel sources-panel"><div className="panel-head"><div><p className="eyebrow">ACQUISITION</p><h2>Sources principales</h2></div></div><div className="source-list">{!stats.sources.length && <p className="muted">Aucune réponse collectée pour le moment.</p>}{stats.sources.map((source, i) => { const total = stats.sources.reduce((a, b) => a + b.count, 0); const pct = Math.round(source.count / total * 100); return <div className="source-row" key={source.name}><span className={`source-dot dot-${i % 4}`} /><div><div className="source-label"><strong>{source.name}</strong><span>{pct} %</span></div><div className="progress"><i style={{ width: `${pct}%` }} /></div></div></div>; })}</div></article>
      </section>
      <section className="split-section"><article className="panel"><div className="panel-head"><div><p className="eyebrow">CAMPAGNES</p><h2>En ce moment</h2></div><Link href="/campaigns" className="text-link">Tout voir <ArrowRight size={16} /></Link></div><div className="campaign-mini-list">{campaigns.slice(0, 3).map(c => <Link href={`/campaigns/${c.id}`} className="campaign-mini" key={c.id}><div className="campaign-icon"><FolderOpen size={20} /></div><div className="campaign-mini-name"><strong>{c.name}</strong><span>{c.forms} formulaire{c.forms > 1 ? "s" : ""} · {c.responses} réponses</span></div><span className={`status-dot ${c.active ? "active" : "draft"}`} /> <ArrowRight size={17} /></Link>)}</div></article>
      <article className="panel"><div className="panel-head"><div><p className="eyebrow">TEMPS RÉEL</p><h2>Dernières réponses</h2></div></div><div className="recent-list">{!stats.recent.length && <p className="muted">Les nouvelles réponses apparaîtront ici.</p>}{stats.recent.slice(0, 4).map((r, i) => <div className="recent-row" key={r.id}><div className={`avatar avatar-color-${i}`}>{r.name.split(" ").map(v => v[0]).join("").slice(0, 2)}</div><div><strong>{r.name}</strong><span>{r.form} · {r.campaign}</span></div><small>{relativeTime(r.created_at)}</small></div>)}</div></article></section>
    </>}
  </div>;
}

function Metric({ icon, label, value, note, positive }: { icon: React.ReactNode; label: string; value: string; note: string; positive?: boolean }) { return <article className="metric-card"><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong><span className={positive ? "positive" : ""}>{positive && "↗ "}{note}</span></article>; }

function LineChart({ data }: { data: { date: string; count: number }[] }) {
  const max = Math.max(...data.map(d => d.count), 1); const points = data.map((d, i) => `${8 + i * 14},${82 - d.count / max * 62}`).join(" ");
  return <div className="line-chart"><svg viewBox="0 0 100 92" preserveAspectRatio="none"><g className="chart-grid"><line x1="0" y1="20" x2="100" y2="20"/><line x1="0" y1="51" x2="100" y2="51"/><line x1="0" y1="82" x2="100" y2="82"/></g><polyline className="chart-line" points={points}/>{data.map((d, i) => <circle key={d.date} className="chart-point" cx={8 + i * 14} cy={82 - d.count / max * 62} r="1.5" />)}</svg><div className="chart-labels">{data.map(d => <span key={d.date}>{day.format(new Date(d.date))}</span>)}</div></div>;
}

function relativeTime(date: string) { const mins = Math.round((Date.now() - new Date(date).getTime()) / 60000); if (mins < 60) return `il y a ${Math.max(1, mins)} min`; const hours = Math.round(mins / 60); if (hours < 24) return `il y a ${hours} h`; return `il y a ${Math.round(hours / 24)} j`; }

