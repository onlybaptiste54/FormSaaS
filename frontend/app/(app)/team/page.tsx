"use client";

import { FormEvent, useEffect, useState } from "react";
import { LoaderCircle, Mail, Plus, ShieldCheck } from "lucide-react";
import { PageHeader, initials } from "@/components/shell";
import { AuthField, validateEmail } from "@/components/auth-layout";
import { Badge, ErrorState, Loading, Toast } from "@/components/ui";
import { api } from "@/lib/api";

type Member = { id: string; full_name: string; email: string; role: string };
type Invitation = { id: string; email: string; role: string; created_at: string; expires_at: string };

const access: Record<string, string> = {
  admin: "Toutes les campagnes",
  creator: "Ses campagnes",
  viewer: "Campagnes partagées",
};

const roles: Record<string, { label: string; text: string }> = {
  admin: { label: "Administrateur", text: "gère l'équipe, les réglages et toutes les campagnes" },
  creator: { label: "Créateur", text: "crée et modifie les campagnes" },
  viewer: { label: "Lecteur", text: "consulte les campagnes sans les modifier" },
};

const shortDate = (value: string) => new Date(value).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });

export default function TeamPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [pending, setPending] = useState<Invitation[]>([]);
  const [error, setError] = useState("");
  const [inviting, setInviting] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("creator");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [listError, setListError] = useState("");
  const [notice, setNotice] = useState("");

  const loadPending = () => api<Invitation[]>("/team/invitations").then(setPending);
  const load = () => {
    setError("");
    Promise.all([api<Member[]>("/team"), api<{ role: string }>("/me")])
      .then(async ([team, me]) => {
        setMembers(team);
        setIsAdmin(me.role === "admin");
        if (me.role === "admin") await loadPending();
      })
      .catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, []);

  function say(text: string) {
    setNotice(text);
    setTimeout(() => setNotice(""), 4000);
  }

  function close() {
    setInviting(false); setEmail(""); setRole("creator"); setSubmitted(false); setFormError("");
  }

  async function invite(e: FormEvent) {
    e.preventDefault(); setSubmitted(true); setFormError("");
    if (validateEmail(email)) return;
    setBusy(true);
    try {
      await api("/team/invitations", { method: "POST", body: JSON.stringify({ email: email.trim(), role }) });
      say(`Invitation envoyée à ${email.trim().toLowerCase()}.`);
      close();
      await loadPending();
    } catch (err) { setFormError(err instanceof Error ? err.message : "L'invitation n'a pas pu être envoyée. Réessayez dans un instant."); }
    setBusy(false);
  }

  async function revoke(invitation: Invitation) {
    setListError("");
    try {
      await api(`/team/invitations/${invitation.id}`, { method: "DELETE" });
      await loadPending();
      say(`Invitation à ${invitation.email} révoquée.`);
    } catch (err) { setListError(err instanceof Error ? err.message : "La révocation a échoué. Réessayez dans un instant."); }
  }

  return <div className="page-wrap">
    <PageHeader eyebrow="COLLABORATION" title="Équipe" description="Contrôlez qui peut créer, consulter et partager vos campagnes." actions={isAdmin && !inviting && <button className="button button-primary" onClick={() => setInviting(true)}><Plus size={17}/>Inviter un membre</button>}/>
    {error ? <ErrorState message={error} onRetry={load}/> : !members ? <Loading/> : <>
      {isAdmin && inviting && <form className="panel invite-panel form-stack" onSubmit={invite} noValidate>
        <h2>Inviter un membre</h2>
        <AuthField label="Email" type="email" autoComplete="off" value={email} onChange={setEmail} validate={validateEmail} submitted={submitted}/>
        <div className="auth-field">
          <label htmlFor="invite-role">Rôle</label>
          <select id="invite-role" value={role} onChange={e => setRole(e.target.value)} aria-describedby="invite-role-hint">
            {Object.entries(roles).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
          </select>
          <p className="field-hint" id="invite-role-hint">{roles[role].label} : {roles[role].text}.</p>
        </div>
        {formError && <p className="form-error">{formError}</p>}
        <div className="invite-actions">
          <button className="button button-primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18}/> : "Envoyer l'invitation"}</button>
          <button type="button" className="button button-secondary" onClick={close} disabled={busy}>Annuler</button>
        </div>
      </form>}
      <div className="panel team-panel">
        <div className="table-head team-head"><span>Membre</span><span>Rôle</span><span>Accès</span></div>
        {members.map((member, index) => <div className="team-row" key={member.id}>
          <div><div className={`avatar avatar-color-${index % 4}`}>{initials(member.full_name)}</div><span><strong>{member.full_name}</strong><small>{member.email}</small></span></div>
          <Badge tone={member.role === "admin" ? "green" : "neutral"}>{member.role === "admin" ? "Admin" : member.role === "creator" ? "Créateur" : "Lecteur"}</Badge>
          <span className="access-label"><ShieldCheck size={16}/>{access[member.role] || "Campagnes partagées"}</span>
        </div>)}
      </div>
      {isAdmin && pending.length > 0 && <div className="panel team-panel pending-panel">
        <div className="table-head"><span>Invitations en attente</span></div>
        {listError && <p className="form-error pending-error">{listError}</p>}
        {pending.map(invitation => <div className="pending-row" key={invitation.id}>
          <span><strong>{invitation.email}</strong><small>{roles[invitation.role]?.label ?? invitation.role} · expire le {shortDate(invitation.expires_at)}</small></span>
          <button className="text-link auth-link" onClick={() => revoke(invitation)}>Révoquer<span className="sr-only"> l&apos;invitation de {invitation.email}</span></button>
        </div>)}
      </div>}
    </>}
    <div className="info-callout"><Mail/><div><strong>Invitations par e-mail</strong><p>Chaque invitation part par e-mail avec un lien personnel, valable 7 jours. La personne choisit son nom et son mot de passe, puis rejoint votre entreprise.</p></div></div>
    {notice && <Toast>{notice}</Toast>}
  </div>;
}
