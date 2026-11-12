"use client";

import { useId, useState } from "react";
import { Check, Eye, EyeOff } from "lucide-react";
import { Logo } from "@/components/logo";

/** Les pages publiques de compte (connexion, mot de passe, invitation) partagent cette mise en page. */
export function AuthLayout({ eyebrow, title, lead, children }: { eyebrow: string; title: string; lead?: string; children?: React.ReactNode }) {
  return <main className="login-page">
    <section className="login-brand">
      <Logo />
      <div className="login-promise"><p className="eyebrow light">DES TUNNELS DE VENTE À VOTRE IMAGE</p><h1>Présentez votre offre. Guidez chaque visiteur.</h1><p>Décrivez votre offre à Luna, publiez vos pages et suivez les passages jusqu’au clic final.</p><div className="promise-list"><span><Check size={17} />Des pages créées avec votre marque</span><span><Check size={17} />Un parcours guidé, étape par étape</span><span><Check size={17} />Des résultats liés à chaque tunnel</span></div></div>
      <p className="brand-foot">Sillage · Nantes, France</p>
    </section>
    <section className="login-panel"><div className="login-box"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2>{lead && <p className="muted">{lead}</p>}{children}</div></section>
  </main>;
}

export const validateEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()) ? "" : "Saisissez une adresse e-mail valide.";
export const validatePassword = (value: string) => value.length >= 12 ? "" : "Le mot de passe doit faire au moins 12 caractères.";
export const validateName = (value: string) => value.trim().length >= 2 ? "" : "Saisissez votre nom complet (2 caractères minimum).";

type FieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  validate: (value: string) => string;
  /** Vrai après un envoi : les erreurs s'affichent même si le champ n'a pas été quitté. */
  submitted: boolean;
  type?: "text" | "email" | "password";
  autoComplete?: string;
  hint?: string;
};

/** Champ validé en quittant le champ ; ensuite l'erreur se met à jour à chaque frappe. */
export function AuthField({ label, value, onChange, validate, submitted, type = "text", autoComplete, hint }: FieldProps) {
  const [touched, setTouched] = useState(false);
  const [show, setShow] = useState(false);
  const id = useId();
  const error = touched || submitted ? validate(value) : "";
  const isPassword = type === "password";
  const input = <input id={id} value={value} onChange={e => onChange(e.target.value)} onBlur={() => setTouched(true)}
    type={isPassword && show ? "text" : type} autoComplete={autoComplete} aria-invalid={error ? true : undefined}
    aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined} />;
  return <div className="auth-field">
    <label htmlFor={id}>{label}</label>
    {isPassword
      ? <div className="password-field">{input}<button type="button" onClick={() => setShow(!show)} aria-label={show ? "Masquer le mot de passe" : "Afficher le mot de passe"}>{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
      : input}
    {error ? <p className="field-error" id={`${id}-error`}>{error}</p> : hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>;
}
