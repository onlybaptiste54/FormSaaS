"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";
import { api } from "@/lib/api";
import { AuthField, AuthLayout, validateName, validatePassword } from "@/components/auth-layout";

type Invitation = { company: string; email: string; role: string };

const roles: Record<string, string> = { admin: "Administrateur", creator: "Créateur", viewer: "Lecteur" };

export default function InvitationPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  // null : vérification en cours.
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [invalid, setInvalid] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const value = window.location.hash.slice(1);
    setToken(value);
    if (!value) { setInvalid("Ce lien ne contient pas de jeton. Ouvrez-le depuis l'e-mail d'invitation."); return; }
    api<Invitation>("/auth/invitation", { method: "POST", body: JSON.stringify({ token: value }) })
      .then(setInvitation)
      .catch(err => setInvalid(err instanceof Error ? err.message : "Impossible de vérifier cette invitation. Réessayez dans un instant."));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault(); setSubmitted(true); setError("");
    if (validateName(fullName) || validatePassword(password)) return;
    setBusy(true);
    try {
      const data = await api<{ access_token: string }>("/auth/accept-invitation", { method: "POST", body: JSON.stringify({ token, full_name: fullName.trim(), password }) });
      localStorage.setItem("sillage_token", data.access_token);
      router.push("/dashboard");
    } catch (err) { setError(err instanceof Error ? err.message : "La création du compte a échoué. Réessayez dans un instant."); setBusy(false); }
  }

  if (invalid) return <AuthLayout eyebrow="INVITATION" title="Invitation indisponible" lead={invalid}>
    <Link href="/" className="text-link auth-link">Aller à la connexion</Link>
  </AuthLayout>;

  if (!invitation) return <AuthLayout eyebrow="INVITATION" title="Vérification de l'invitation" lead="Un instant.">
    <div className="form-stack" aria-busy="true"><div className="skeleton-block" /><div className="skeleton-block" /><div className="skeleton-block" /><div className="skeleton-block skeleton-button" /></div>
  </AuthLayout>;

  return <AuthLayout eyebrow="INVITATION" title={`Rejoindre ${invitation.company}`} lead={`Vous rejoignez l'équipe avec le rôle ${roles[invitation.role] ?? invitation.role}.`}>
    <form onSubmit={submit} className="form-stack" noValidate>
      <div className="auth-field">
        <label htmlFor="invitation-email">Email</label>
        <input id="invitation-email" value={invitation.email} readOnly />
      </div>
      <AuthField label="Nom complet" autoComplete="name" value={fullName} onChange={setFullName} validate={validateName} submitted={submitted} />
      <AuthField label="Mot de passe" type="password" autoComplete="new-password" value={password} onChange={setPassword} validate={validatePassword} submitted={submitted} hint="12 caractères minimum." />
      {error && <p className="form-error">{error}</p>}
      <button className="button button-primary button-large" disabled={busy}>{busy ? <LoaderCircle className="spin" size={19} /> : "Créer mon compte"}</button>
    </form>
  </AuthLayout>;
}
