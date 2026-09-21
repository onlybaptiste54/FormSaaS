"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, ArchiveRestore, Copy, ExternalLink, FileText, Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, EmptyState, ErrorState, Loading, Toast } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

const filters = [
  { key: "all", label: "Toutes" },
  { key: "active", label: "Actives" },
  { key: "draft", label: "Brouillons" },
  { key: "archived", label: "Archivées" },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<{ text: string; undo?: () => void } | null>(null);

  const archivedView = filter === "archived";
  const load = () => {
    setError("");
    setCampaigns(null);
    api<Campaign[]>(`/campaigns?archived=${archivedView}`)
      .then(setCampaigns)
      .catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, [archivedView]);

  const filtered = useMemo(() => (campaigns || []).filter(campaign =>
    (filter === "all" || archivedView || campaign.status === filter) &&
    `${campaign.name} ${campaign.description}`.toLowerCase().includes(query.toLowerCase()),
  ), [campaigns, query, filter, archivedView]);

  function flash(text: string, undo?: () => void) {
    setNotice({ text, undo });
    setTimeout(() => setNotice(null), undo ? 8000 : 3000);
  }

  async function setArchived(campaign: Campaign, archived: boolean) {
    await api(`/campaigns/${campaign.id}`, { method: "PATCH", body: JSON.stringify({ archived }) });
    load();
    if (archived) flash(`« ${campaign.name} » archivée`, () => void setArchived(campaign, false));
    else flash(`« ${campaign.name} » restaurée`);
  }

  async function duplicate(id: string) {
    await api(`/campaigns/${id}/duplicate`, { method: "POST" });
    load();
    flash("Copie créée");
  }

  return <div className="page-wrap">
    <PageHeader eyebrow="GESTION" title="Campagnes" description="Créez, suivez et partagez tous vos formulaires." actions={<Link href="/campaigns/new" className="button button-primary"><Plus size={18}/>Créer une campagne</Link>}/>
    <div className="toolbar">
      <div className="search-box"><Search size={18}/><input placeholder="Rechercher une campagne…" value={query} onChange={event => setQuery(event.target.value)}/></div>
      <div className="segment-control">{filters.map(item => <button key={item.key} className={filter === item.key ? "selected" : ""} onClick={() => setFilter(item.key)}>{item.label}</button>)}</div>
    </div>

    {error ? <ErrorState message={error} onRetry={load}/> : campaigns === null ? <Loading/> : filtered.length === 0 ? (
      <EmptyState icon={<FileText/>} title={archivedView ? "Aucune campagne archivée" : "Aucune campagne"} text={archivedView ? "Les campagnes que vous archivez seront rangées ici." : "Essayez une autre recherche ou créez votre première campagne."} action={!archivedView && <Link href="/campaigns/new" className="button button-primary">Créer maintenant</Link>}/>
    ) : (
      <div className="campaign-table panel">
        <div className="table-head"><span>Campagne</span><span>Statut</span><span>Réponses</span><span>Conversion</span><span>Mise à jour</span><span/></div>
        {filtered.map(campaign => <div className="table-row" key={campaign.id}>
          <Link className="campaign-cell" href={`/campaigns/${campaign.id}`}><div className="campaign-icon"><FileText size={20}/></div><div><strong>{campaign.name}</strong><span>{campaign.description}</span></div></Link>
          <span><Badge tone={campaign.status === "active" ? "green" : "amber"}>{campaign.status === "active" ? "Active" : "Brouillon"}</Badge></span>
          <strong>{campaign.responses}</strong>
          <span>{campaign.conversion} %</span>
          <span>{new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(new Date(campaign.updated_at))}</span>
          <div className="row-actions">
            {archivedView ? (
              <button className="icon-button" onClick={() => void setArchived(campaign, false)} title="Restaurer" aria-label={`Restaurer ${campaign.name}`}><ArchiveRestore size={17}/></button>
            ) : <>
              <a className="icon-button" href={`/forms/${campaign.slug}?preview=1`} target="_blank" title="Ouvrir" aria-label={`Ouvrir ${campaign.name}`}><ExternalLink size={17}/></a>
              <button className="icon-button" onClick={() => void duplicate(campaign.id)} title="Dupliquer" aria-label={`Dupliquer ${campaign.name}`}><Copy size={17}/></button>
              <button className="icon-button" onClick={() => void setArchived(campaign, true)} title="Archiver" aria-label={`Archiver ${campaign.name}`}><Archive size={17}/></button>
            </>}
          </div>
        </div>)}
      </div>
    )}

    {notice && <Toast>{notice.text}{notice.undo && <button className="toast-undo" onClick={() => { notice.undo?.(); setNotice(null); }}>Annuler</button>}</Toast>}
  </div>;
}
