"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Plus, Waypoints } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { EmptyState, ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { SalesTunnel } from "@/lib/types";

export default function SalesFunnels() {
  const [funnels, setFunnels] = useState<SalesTunnel[] | null>(null);
  const [error, setError] = useState("");
  const load = () => { setError(""); void api<SalesTunnel[]>("/sales-funnels").then(setFunnels).catch(reason => setError(reason instanceof Error ? reason.message : "Impossible de charger les tunnels.")); };
  useEffect(load, []);

  return <div className="page-wrap sales-list"><PageHeader eyebrow="VENTE" title="Tunnels de vente" description="Créez un parcours pour présenter votre offre et guider les visiteurs vers une action." actions={<Link href="/funnels/new" className="button button-primary"><Plus size={18}/>Nouveau tunnel</Link>}/>
    {error ? <ErrorState message={error} onRetry={load}/> : !funnels ? <Loading/> : !funnels.length
      ? <EmptyState icon={<Waypoints/>} title="Votre premier tunnel commence ici" text="Décrivez votre offre, vos clients et les raisons de vous choisir. Luna prépare les pages ; vous décidez quand les publier." action={<Link href="/funnels/new" className="button button-primary">Créer un tunnel</Link>}/>
      : <div className="sales-cards">{funnels.map(funnel => <Link key={funnel.id} href={`/funnels/${funnel.id}`} className="panel sales-card"><span className="sales-card-icon"><Waypoints size={22}/></span><span className="sales-card-copy"><strong>{funnel.name}</strong><small>{funnel.brief.offer}</small><span>{funnel.pages.length} étapes · {funnel.goal_label}</span></span><span className={funnel.status === "active" ? "badge badge-green" : "badge badge-amber"}>{funnel.status === "active" ? "En ligne" : "Brouillon"}</span><ArrowRight size={18}/></Link>)}</div>}
  </div>;
}
