"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, FileCheck2, FilePen, FileText, MousePointerClick, Plus } from "lucide-react";
import { PageHeader, useMe } from "@/components/shell";
import { ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign, Stats } from "@/lib/types";

const day = new Intl.DateTimeFormat("fr-FR", { weekday: "short" });
const today = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });

export default function Dashboard() {
  const me = useMe();
  const [stats, setStats] = useState<Stats | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    Promise.all([api<Stats>("/stats"), api<Campaign[]>("/campaigns")])
      .then(([s, c]) => { setStats(s); setCampaigns(c); })
      .catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, []);
  const firstName = me?.full_name.split(" ")[0];
  const drafts = campaigns.filter(c => c.status !== "active").length;
  return <div className="page-wrap dashboard-page"><PageHeader eyebrow={today.format(new Date()).toUpperCase()} title={firstName ? `Bonjour ${firstName}.` : "Bonjour."} description="Voici ce qui s’est passé depuis votre dernière visite." actions={<Link href="/campaigns/new" className="button button-primary"><Plus size={18} />Créer une campagne</Link>} />
    {error ? <ErrorState message={error} onRetry={load} /> : !stats ? <Loading /> : <>
      <section className="metric-grid">
        <Metric icon={<FileText />} label="Campagnes actives" value={stats.active.toString()} note={`${stats.campaigns} au total`} />
        <Metric icon={<FileCheck2 />} label="Réponses collectées" value={stats.responses.toLocaleString("fr-FR")} note={`+${stats.week_responses} cette semaine`} positive />
        <Metric icon={<MousePointerClick />} label="Taux de conversion" value={`${stats.conversion} %`} note="Toutes campagnes" />
        <Metric icon={<FilePen />} label="Brouillons" value={drafts.toString()} note={drafts ? "À publier" : "Tout est publié"} />
      </section>
      <section className="dashboard-grid">
        <article className="panel chart-panel"><div className="panel-head"><div><p className="eyebrow">ACTIVITÉ</p><h2>Réponses sur 7 jours</h2></div><span className="chart-total">{stats.week_responses} <small>réponses</small></span></div><LineChart data={stats.daily} /></article>
        <article className="panel sources-panel"><div className="panel-head"><div><p className="eyebrow">ACQUISITION</p><h2>Sources principales</h2></div></div><div className="source-list">{!stats.sources.length && <p className="muted">Aucune réponse collectée pour le moment.</p>}{stats.sources.map((source, i) => { const total = stats.sources.reduce((a, b) => a + b.count, 0); const pct = Math.round(source.count / total * 100); return <div className="source-row" key={source.name}><span className={`source-dot dot-${i % 4}`} /><div><div className="source-label"><strong>{source.name}</strong><span>{pct} %</span></div><div className="progress"><i style={{ width: `${pct}%` }} /></div></div></div>; })}</div></article>
      </section>
      <section className="split-section"><article className="panel"><div className="panel-head"><div><p className="eyebrow">CAMPAGNES</p><h2>En ce moment</h2></div><Link href="/campaigns" className="text-link">Tout voir <ArrowRight size={16} /></Link></div><div className="campaign-mini-list">{campaigns.slice(0, 3).map(c => <Link href={`/campaigns/${c.id}`} className="campaign-mini" key={c.id}><div className="campaign-icon"><FileText size={20} /></div><div className="campaign-mini-name"><strong>{c.name}</strong><span>{c.responses} réponses · {c.conversion}% de conversion</span></div><span className={`status-dot ${c.status}`} /> <ArrowRight size={17} /></Link>)}</div></article>
      <article className="panel"><div className="panel-head"><div><p className="eyebrow">TEMPS RÉEL</p><h2>Dernières réponses</h2></div></div><div className="recent-list">{!stats.recent.length && <p className="muted">Les nouvelles réponses apparaîtront ici.</p>}{stats.recent.slice(0, 4).map((r, i) => <div className="recent-row" key={r.id}><div className={`avatar avatar-color-${i}`}>{r.name.split(" ").map(v => v[0]).join("").slice(0, 2)}</div><div><strong>{r.name}</strong><span>{r.campaign}</span></div><small>{relativeTime(r.created_at)}</small></div>)}</div></article></section>
    </>}
  </div>;
}

function Metric({ icon, label, value, note, positive }: { icon: React.ReactNode; label: string; value: string; note: string; positive?: boolean }) { return <article className="metric-card"><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong><span className={positive ? "positive" : ""}>{positive && "↗ "}{note}</span></article>; }

function LineChart({ data }: { data: { date: string; count: number }[] }) {
  const max = Math.max(...data.map(d => d.count), 1); const points = data.map((d, i) => `${8 + i * 14},${82 - d.count / max * 62}`).join(" ");
  return <div className="line-chart"><svg viewBox="0 0 100 92" preserveAspectRatio="none"><g className="chart-grid"><line x1="0" y1="20" x2="100" y2="20"/><line x1="0" y1="51" x2="100" y2="51"/><line x1="0" y1="82" x2="100" y2="82"/></g><polyline className="chart-line" points={points}/>{data.map((d, i) => <circle key={d.date} className="chart-point" cx={8 + i * 14} cy={82 - d.count / max * 62} r="1.5" />)}</svg><div className="chart-labels">{data.map(d => <span key={d.date}>{day.format(new Date(d.date))}</span>)}</div></div>;
}

function relativeTime(date: string) { const mins = Math.round((Date.now() - new Date(date).getTime()) / 60000); if (mins < 60) return `il y a ${Math.max(1, mins)} min`; const hours = Math.round(mins / 60); if (hours < 24) return `il y a ${hours} h`; return `il y a ${Math.round(hours / 24)} j`; }

