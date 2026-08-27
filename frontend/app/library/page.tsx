"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarDays, MessageSquare, Search, Star, UserRound } from "lucide-react";
import { PageHeader, Shell } from "@/components/shell";

const templates=[{title:"Contact artisan",category:"Contact",text:"Qualification courte pour intervention, urgence et rappel.",icon:UserRound},{title:"Satisfaction client",category:"Sondage",text:"Note globale, recommandation et commentaire libre.",icon:Star},{title:"Inscription événement",category:"Information",text:"Coordonnées et nombre de participants.",icon:CalendarDays},{title:"Retour d’expérience",category:"Sondage",text:"Une écoute structurée après une prestation.",icon:MessageSquare},{title:"Contact commerce",category:"Contact",text:"Transformez les visiteurs en demandes qualifiées.",icon:UserRound},{title:"Prise de contact premium",category:"Contact",text:"Un accueil soigné pour les services haut de gamme.",icon:Star}];
export default function LibraryPage(){const[q,setQ]=useState("");const filtered=templates.filter(t=>`${t.title} ${t.category}`.toLowerCase().includes(q.toLowerCase()));return <Shell><div className="page-wrap"><PageHeader eyebrow="INSPIRATION" title="Bibliothèque" description="Des points de départ éprouvés, personnalisés par Luna pour votre marque."/><div className="library-search search-box"><Search size={19}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Rechercher : contact artisan, sondage restaurant…"/></div><div className="template-grid">{filtered.map(({title,category,text,icon:Icon})=><article className="template-card panel" key={title}><div className="template-top"><div className="metric-icon"><Icon/></div><span>{category}</span></div><h2>{title}</h2><p>{text}</p><Link href={`/campaigns/new?template=${encodeURIComponent(title)}`} className="text-link">Personnaliser avec Luna <ArrowRight size={16}/></Link></article>)}</div></div></Shell>}

