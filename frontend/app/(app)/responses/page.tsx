"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BarChart3 } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign, Stats } from "@/lib/types";

export default function ResponsesPage(){const [data,setData]=useState<{stats:Stats;campaigns:Campaign[]}|null>(null);useEffect(()=>{Promise.all([api<Stats>("/stats"),api<Campaign[]>("/campaigns")]).then(([stats,campaigns])=>setData({stats,campaigns}));},[]);return <div className="page-wrap"><PageHeader eyebrow="COLLECTE" title="Réponses" description="Une vue claire sur les contacts collectés par vos campagnes."/>{!data?<Loading/>:<><section className="metric-grid metric-grid-3"><article className="metric-card"><p>Total collecté</p><strong>{data.stats.responses}</strong><span>Toutes campagnes</span></article><article className="metric-card"><p>7 derniers jours</p><strong>{data.stats.week_responses}</strong><span className="positive">↗ Activité récente</span></article><article className="metric-card"><p>Conversion moyenne</p><strong>{data.stats.conversion} %</strong><span>Visite → réponse</span></article></section><article className="panel response-hub"><div className="panel-head"><div><p className="eyebrow">PAR CAMPAGNE</p><h2>Accéder aux données</h2></div></div>{data.campaigns.map(c=><Link href={`/campaigns/${c.id}`} key={c.id}><div className="campaign-icon"><BarChart3 size={19}/></div><div><strong>{c.name}</strong><span>{c.responses} réponses</span></div><b>{c.conversion}%</b><ArrowRight size={17}/></Link>)}</article></>}</div>}

