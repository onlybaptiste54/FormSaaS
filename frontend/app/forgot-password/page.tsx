"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { LoaderCircle } from "lucide-react";
import { api } from "@/lib/api";
import { AuthField, AuthLayout, validateEmail } from "@/components/auth-layout";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault(); setSubmitted(true); setError("");
    if (validateEmail(email)) return;
    setBusy(true);
    try { await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email: email.trim() }) }); setSent(true); }
    catch (err) { setError(err instanceof Error ? err.message : "L'envoi a échoué. Réessayez dans un instant."); }
    setBusy(false);
  }

  if (sent) return <AuthLayout eyebrow="MOT DE PASSE OUBLIÉ" title="Consultez votre boîte mail" lead="Si un compte existe pour cette adresse, un lien vient d'y être envoyé. Il reste valable une heure.">
    <Link href="/" className="text-link auth-link">Retour à la connexion</Link>
  </AuthLayout>;

  return <AuthLayout eyebrow="MOT DE PASSE OUBLIÉ" title="Recevoir un lien" lead="Saisissez l'adresse de votre compte. Vous recevrez un lien pour choisir un nouveau mot de passe.">
    <form onSubmit={submit} className="form-stack" noValidate>
      <AuthField label="Email" type="email" autoComplete="email" value={email} onChange={setEmail} validate={validateEmail} submitted={submitted} />
      {error && <p className="form-error">{error}</p>}
      <button className="button button-primary button-large" disabled={busy}>{busy ? <LoaderCircle className="spin" size={19} /> : "Envoyer le lien"}</button>
      <Link href="/" className="text-link auth-link">Retour à la connexion</Link>
    </form>
  </AuthLayout>;
}
