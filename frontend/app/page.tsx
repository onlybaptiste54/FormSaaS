"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { AuthLayout } from "@/components/auth-layout";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [demo, setDemo] = useState(false);
  useEffect(() => {
    if (!getToken()) return;
    api("/me").then(() => router.replace("/dashboard")).catch(() => undefined);
  }, [router]);
  // Le compte de démonstration n'existe qu'hors production : c'est l'API qui le dit.
  useEffect(() => {
    api<{ demo?: boolean }>("/health").then(data => {
      if (!data.demo) return;
      setDemo(true); setEmail("demo@sillage.fr"); setPassword("demo1234");
    }).catch(() => undefined);
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { const data = await api<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); localStorage.setItem("sillage_token", data.access_token); router.push("/dashboard"); }
    catch (err) { setError(err instanceof Error ? err.message : "Connexion impossible"); setBusy(false); }
  }
  return <AuthLayout eyebrow="BON RETOUR PARMI NOUS" title="Connectez-vous" lead="Retrouvez vos tunnels et leurs résultats.">
    <form onSubmit={submit} className="form-stack"><label>Email<input value={email} onChange={e => setEmail(e.target.value)} type="email" autoComplete="email" required /></label><label>Mot de passe<div className="password-field"><input value={password} onChange={e => setPassword(e.target.value)} type={show ? "text" : "password"} autoComplete="current-password" required /><button type="button" onClick={() => setShow(!show)} aria-label="Afficher le mot de passe">{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label><Link href="/forgot-password" className="text-link auth-link auth-link-end">Mot de passe oublié ?</Link>{error && <p className="form-error">{error}</p>}<button className="button button-primary button-large" disabled={busy}>{busy ? <LoaderCircle className="spin" size={19} /> : <>Se connecter <ArrowRight size={18} /></>}</button></form>{demo && <div className="demo-note"><strong>Compte de démonstration</strong><span>Les identifiants sont déjà renseignés.</span></div>}
  </AuthLayout>;
}
