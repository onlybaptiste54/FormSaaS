"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, Copy, ExternalLink, FileText, MoreHorizontal, Plus, Search } from "lucide-react";
import { PageHeader, Shell } from "@/components/shell";
import { Badge, EmptyState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null); const [query, setQuery] = useState(""); const [filter, setFilter] = useState("all");
  const load = () => api<Campaign[]>("/campaigns").then(setCampaigns);
  useEffect(() => { void load(); }, []);
  const filtered = useMemo(() => (campaigns || []).filter(c => (filter === "all" || c.status === filter) && `${c.name} ${c.description}`.toLowerCase().includes(query.toLowerCase())), [campaigns, query, filter]);
  async function duplicate(id: string) { await api(`/campaigns/${id}/duplicate`, { method: "POST" }); load(); }
  async function archive(id: string) { await api(`/campaigns/${id}`, { method: "PATCH", body: JSON.stringify({ archived: true }) }); load(); }
  return <Shell><div className="page-wrap"><PageHeader eyebrow="GESTION" title="Campagnes" description="Créez, suivez et partagez tous vos formulaires." actions={<Link href="/campaigns/new" className="button button-primary"><Plus size={18}/>Créer une campagne</Link>}/><div className="toolbar"><div className="search-box"><Search size={18}/><input placeholder="Rechercher une campagne…" value={query} onChange={e => setQuery(e.target.value)}/></div><div className="segment-control"><button className={filter === "all" ? "selected" : ""} onClick={() => setFilter("all")}>Toutes</button><button className={filter === "active" ? "selected" : ""} onClick={() => setFilter("active")}>Actives</button><button className={filter === "draft" ? "selected" : ""} onClick={() => setFilter("draft")}>Brouillons</button></div></div>
    {campaigns === null ? <Loading/> : filtered.length === 0 ? <EmptyState icon={<FileText/>} title="Aucune campagne" text="Essayez une autre recherche ou créez votre première campagne." action={<Link href="/campaigns/new" className="button button-primary">Créer maintenant</Link>}/> : <div className="campaign-table panel"><div className="table-head"><span>Campagne</span><span>Statut</span><span>Réponses</span><span>Conversion</span><span>Mise à jour</span><span/></div>{filtered.map(c => <div className="table-row" key={c.id}><Link className="campaign-cell" href={`/campaigns/${c.id}`}><div className="campaign-icon"><FileText size={20}/></div><div><strong>{c.name}</strong><span>{c.description}</span></div></Link><span><Badge tone={c.status === "active" ? "green" : "amber"}>{c.status === "active" ? "Active" : "Brouillon"}</Badge></span><strong>{c.responses}</strong><span>{c.conversion} %</span><span>{new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(new Date(c.updated_at))}</span><div className="row-actions"><a className="icon-button" href={`/forms/${c.slug}`} target="_blank" title="Ouvrir"><ExternalLink size={17}/></a><button className="icon-button" onClick={() => duplicate(c.id)} title="Dupliquer"><Copy size={17}/></button><button className="icon-button" onClick={() => archive(c.id)} title="Archiver"><Archive size={17}/></button></div></div>)}</div>}
  </div></Shell>;
}
