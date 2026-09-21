"use client";

import { useEffect, useState } from "react";
import { Mail, ShieldCheck } from "lucide-react";
import { PageHeader, initials } from "@/components/shell";
import { Badge, ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";

type Member = { id: string; full_name: string; email: string; role: string };

const access: Record<string, string> = {
  admin: "Toutes les campagnes",
  creator: "Ses campagnes",
  viewer: "Campagnes partagées",
};

export default function TeamPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState("");
  const load = () => {
    setError("");
    api<Member[]>("/team").then(setMembers).catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, []);

  return <div className="page-wrap">
    <PageHeader eyebrow="COLLABORATION" title="Équipe" description="Contrôlez qui peut créer, consulter et partager vos campagnes." actions={<span className="badge badge-neutral">Invitations bientôt disponibles</span>}/>
    {error ? <ErrorState message={error} onRetry={load}/> : !members ? <Loading/> : <div className="panel team-panel">
      <div className="table-head team-head"><span>Membre</span><span>Rôle</span><span>Accès</span></div>
      {members.map((member, index) => <div className="team-row" key={member.id}>
        <div><div className={`avatar avatar-color-${index % 4}`}>{initials(member.full_name)}</div><span><strong>{member.full_name}</strong><small>{member.email}</small></span></div>
        <Badge tone={member.role === "admin" ? "green" : "neutral"}>{member.role === "admin" ? "Admin" : member.role === "creator" ? "Créateur" : "Lecteur"}</Badge>
        <span className="access-label"><ShieldCheck size={16}/>{access[member.role] || "Campagnes partagées"}</span>
      </div>)}
    </div>}
    <div className="info-callout"><Mail/><div><strong>Invitations sécurisées</strong><p>Chaque membre recevra un lien personnel. Les droits pourront être modifiés à tout moment.</p></div></div>
  </div>;
}
