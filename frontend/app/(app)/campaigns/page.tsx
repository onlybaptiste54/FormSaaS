"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, ArchiveRestore, FolderOpen, Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Badge, EmptyState, ErrorState, Loading, Toast } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

const filters = [
  { key: "all", label: "Toutes" },
  { key: "active", label: "Actives" },
  { key: "archived", label: "Archivées" },
];

const shortDate = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

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
    (filter !== "active" || campaign.active > 0) &&
    `${campaign.name} ${campaign.client} ${campaign.objective}`.toLowerCase().includes(query.toLowerCase()),
  ), [campaigns, query, filter]);

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

  return <div className="page-wrap">
    <PageHeader eyebrow="GESTION" title="Campagnes" description="Chaque campagne regroupe les formulaires d’un client, d’un événement ou d’une opération." actions={<Link href="/campaigns/new" className="button button-primary"><Plus size={18}/>Créer une campagne</Link>}/>
    <div className="toolbar">
      <div className="search-box"><Search size={18}/><input placeholder="Rechercher une campagne…" value={query} onChange={event => setQuery(event.target.value)}/></div>
      <div className="segment-control">{filters.map(item => <button key={item.key} className={filter === item.key ? "selected" : ""} onClick={() => setFilter(item.key)}>{item.label}</button>)}</div>
    </div>

    {error ? <ErrorState message={error} onRetry={load}/> : campaigns === null ? <Loading/> : filtered.length === 0 ? (
      <EmptyState icon={<FolderOpen/>} title={archivedView ? "Aucune campagne archivée" : "Aucune campagne"} text={archivedView ? "Les campagnes que vous archivez seront rangées ici." : "Créez une campagne, puis ajoutez-y autant de formulaires que nécessaire."} action={!archivedView && <Link href="/campaigns/new" className="button button-primary">Créer maintenant</Link>}/>
    ) : (
      <div className="campaign-table panel">
        <div className="table-head"><span>Campagne</span><span>Formulaires</span><span>Réponses</span><span>Conversion</span><span>Activité</span><span/></div>
        {filtered.map(campaign => <div className="table-row" key={campaign.id}>
          <Link className="campaign-cell" href={`/campaigns/${campaign.id}`}><div className="campaign-icon"><FolderOpen size={20}/></div><div><strong>{campaign.name}</strong><span>{campaign.client || campaign.objective || "Sans client renseigné"}</span></div></Link>
          <span className="campaign-forms-cell">
            <strong>{campaign.forms}</strong>
            {campaign.active > 0 ? <Badge tone="green">{campaign.active} en ligne</Badge> : <Badge tone="amber">Hors ligne</Badge>}
          </span>
          <strong>{campaign.responses}</strong>
          <span>{campaign.conversion} %</span>
          <span>{shortDate.format(new Date(campaign.last_activity))}</span>
          <div className="row-actions">
            {archivedView
              ? <button className="icon-button" onClick={() => void setArchived(campaign, false)} title="Restaurer" aria-label={`Restaurer ${campaign.name}`}><ArchiveRestore size={17}/></button>
              : <button className="icon-button" onClick={() => void setArchived(campaign, true)} title="Archiver" aria-label={`Archiver ${campaign.name}`}><Archive size={17}/></button>}
          </div>
        </div>)}
      </div>
    )}

    {notice && <Toast>{notice.text}{notice.undo && <button className="toast-undo" onClick={() => { notice.undo?.(); setNotice(null); }}>Annuler</button>}</Toast>}
  </div>;
}
