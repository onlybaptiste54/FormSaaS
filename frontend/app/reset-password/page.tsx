"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { LoaderCircle } from "lucide-react";
import { api } from "@/lib/api";
import { AuthField, AuthLayout, validatePassword } from "@/components/auth-layout";

export default function ResetPasswordPage() {
  // undefined : le jeton n'est pas encore lu (le fragment n'existe que dans le navigateur).
  const [token, setToken] = useState<string | undefined>();
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setToken(window.location.hash.slice(1)); }, []);

  async function submit(e: FormEvent) {
    e.preventDefault(); setSubmitted(true); setError("");
    if (validatePassword(password)) return;
    setBusy(true);
    try { await api("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) }); setDone(true); }
    catch (err) { setError(err instanceof Error ? err.message : "L'enregistrement a échoué. Réessayez dans un instant."); }
    setBusy(false);
  }

  if (token === undefined) return <AuthLayout eyebrow="NOUVEAU MOT DE PASSE" title="Nouveau mot de passe" />;

  if (!token) return <AuthLayout eyebrow="NOUVEAU MOT DE PASSE" title="Lien incomplet" lead="Ce lien ne contient pas de jeton. Ouvrez-le depuis l'e-mail reçu, ou demandez-en un nouveau.">
    <Link href="/forgot-password" className="text-link auth-link">Demander un nouveau lien</Link>
  </AuthLayout>;

  if (done) return <AuthLayout eyebrow="NOUVEAU MOT DE PASSE" title="Mot de passe enregistré" lead="Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.">
    <Link href="/" className="button button-primary button-large">Se connecter</Link>
  </AuthLayout>;

  return <AuthLayout eyebrow="NOUVEAU MOT DE PASSE" title="Choisissez un mot de passe" lead="Ce mot de passe remplace l'ancien.">
    <form onSubmit={submit} className="form-stack" noValidate>
      <AuthField label="Nouveau mot de passe" type="password" autoComplete="new-password" value={password} onChange={setPassword} validate={validatePassword} submitted={submitted} hint="12 caractères minimum." />
      {error && <><p className="form-error">{error}</p><Link href="/forgot-password" className="text-link auth-link">Demander un nouveau lien</Link></>}
      <button className="button button-primary button-large" disabled={busy}>{busy ? <LoaderCircle className="spin" size={19} /> : "Enregistrer le mot de passe"}</button>
    </form>
  </AuthLayout>;
}
