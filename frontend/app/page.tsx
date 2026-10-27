"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { Logo } from "@/components/logo";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("demo@sillage.fr");
  const [password, setPassword] = useState("demo1234");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!getToken()) return;
    api("/me").then(() => router.replace("/dashboard")).catch(() => undefined);
  }, [router]);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { const data = await api<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); localStorage.setItem("sillage_token", data.access_token); router.push("/dashboard"); }
    catch (err) { setError(err instanceof Error ? err.message : "Connexion impossible"); setBusy(false); }
  }
  return <main className="login-page">
    <section className="login-brand">
      <Logo />
      <div className="login-promise"><p className="eyebrow light">DES TUNNELS DE VENTE À VOTRE IMAGE</p><h1>Présentez votre offre. Guidez chaque visiteur.</h1><p>Décrivez votre offre à Luna, publiez vos pages et suivez les passages jusqu’au clic final.</p><div className="promise-list"><span><Check size={17} />Des pages créées avec votre marque</span><span><Check size={17} />Un parcours guidé, étape par étape</span><span><Check size={17} />Des résultats liés à chaque tunnel</span></div></div>
      <p className="brand-foot">Sillage · Nantes, France</p>
    </section>
    <section className="login-panel"><div className="login-box"><p className="eyebrow">BON RETOUR PARMI NOUS</p><h2>Connectez-vous</h2><p className="muted">Retrouvez vos tunnels et leurs résultats.</p><form onSubmit={submit} className="form-stack"><label>Email<input value={email} onChange={e => setEmail(e.target.value)} type="email" autoComplete="email" required /></label><label>Mot de passe<div className="password-field"><input value={password} onChange={e => setPassword(e.target.value)} type={show ? "text" : "password"} autoComplete="current-password" required /><button type="button" onClick={() => setShow(!show)} aria-label="Afficher le mot de passe">{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></label>{error && <p className="form-error">{error}</p>}<button className="button button-primary button-large" disabled={busy}>{busy ? <LoaderCircle className="spin" size={19} /> : <>Se connecter <ArrowRight size={18} /></>}</button></form><div className="demo-note"><strong>Compte de démonstration</strong><span>Les identifiants sont déjà renseignés.</span></div><p className="legal-note">En continuant, vous acceptez nos conditions d’utilisation et notre politique de confidentialité.</p></div></section>
  </main>;
}
