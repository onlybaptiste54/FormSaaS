"use client";

import { Mail, Plus, ShieldCheck } from "lucide-react";
import { PageHeader, Shell } from "@/components/shell";
import { Badge } from "@/components/ui";
const members=[{name:"Camille Martin",email:"demo@sillage.fr",role:"Admin",initials:"CM"},{name:"Nora Garcia",email:"nora@atelier-rivage.fr",role:"Créateur",initials:"NG"},{name:"Paul Richard",email:"paul@atelier-rivage.fr",role:"Lecteur",initials:"PR"}];
export default function TeamPage(){return <Shell><div className="page-wrap"><PageHeader eyebrow="COLLABORATION" title="Équipe" description="Contrôlez qui peut créer, consulter et partager vos campagnes." actions={<button className="button button-primary"><Plus size={18}/>Inviter un membre</button>}/><div className="panel team-panel"><div className="table-head team-head"><span>Membre</span><span>Rôle</span><span>Accès</span></div>{members.map((m,i)=><div className="team-row" key={m.email}><div><div className={`avatar avatar-color-${i}`}>{m.initials}</div><span><strong>{m.name}</strong><small>{m.email}</small></span></div><Badge tone={m.role==="Admin"?"green":"neutral"}>{m.role}</Badge><span className="access-label"><ShieldCheck size={16}/>{m.role==="Admin"?"Toutes les campagnes":m.role==="Créateur"?"Ses campagnes":"Campagnes partagées"}</span></div>)}</div><div className="info-callout"><Mail/><div><strong>Invitations sécurisées</strong><p>Chaque membre reçoit un lien personnel. Les droits peuvent être modifiés à tout moment.</p></div></div></div></Shell>}

