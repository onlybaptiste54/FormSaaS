"use client";

import { Check, ChevronDown, Send } from "lucide-react";
import { backgroundClassName, designClassNames, formStyleVars } from "@/lib/form-design";
import { thankYouTitle } from "@/lib/form-text";
import type { Field, FormContent, FormDesign } from "@/lib/types";

/** Donnees minimales pour dessiner un formulaire, d'ou qu'elles viennent. */
export type RenderableForm = {
  name: string;
  description: string;
  fields: Field[];
  design: FormDesign;
  content?: FormContent;
  thank_you?: Record<string, string>;
};

export type RendererMode = "edit" | "public" | "thumb";

type Props = {
  form: RenderableForm;
  company: { name: string; legal_name?: string; address?: string; dpo_email?: string };
  mode: RendererMode;
  view?: "form" | "thanks";
  values?: Record<string, string | number>;
  consent?: boolean;
  errors?: Record<string, string>;
  busy?: boolean;
  error?: string;
  onChange?: (id: string, value: string | number) => void;
  onConsent?: (value: boolean) => void;
  onSubmit?: (event: React.FormEvent) => void;
};

/** Secours pour une campagne enregistree avant que ces textes soient des donnees. */
const FALLBACK_CONTENT: FormContent = {
  eyebrow: "PRENONS CONTACT",
  submit_label: "Envoyer ma réponse",
  trust_note: "Vos données sont protégées et utilisées uniquement pour traiter votre demande.",
};

function monogram(name: string) {
  return name.split(" ").map(word => word[0]).join("").slice(0, 2).toUpperCase();
}

/**
 * Rendu unique du formulaire : l'apercu de l'editeur, la page publique et les
 * vignettes de la bibliotheque partagent ce composant, donc le meme resultat.
 * Chaque noeud porte un data-luna-id : il sert a savoir ce qu'une selection
 * rectangulaire contient, il n'a aucun effet visuel.
 */
export function FormRenderer({ form, company, mode, view = "form", values = {}, consent = false, errors = {}, busy = false, error, onChange, onConsent, onSubmit }: Props) {
  const interactive = mode === "public";
  const content = { ...FALLBACK_CONTENT, ...form.content };
  const cardClass = `public-card ${designClassNames(form.design)}`;
  const legal = <footer data-luna-id="footer">
    {company.legal_name || company.name}{company.address ? ` · ${company.address}` : ""}
    {company.dpo_email && <> · <a href={`mailto:${company.dpo_email}`}>Vos données</a></>}
  </footer>;

  if (view === "thanks") {
    const thanks = form.thank_you || {};
    return <div className={`${cardClass} thank-you-card`} data-luna-id="card">
      <div className="public-brand" data-luna-id="brand"><span>{monogram(company.name)}</span><strong>{company.name}</strong></div>
      <div className="thanks-check"><Check/></div>
      <h1 data-luna-id="thanks.title">{thankYouTitle(thanks.title, values)}</h1>
      <p data-luna-id="thanks.message">{thanks.message}</p>
      {thanks.action !== "none" && thanks.button_url && <a href={interactive ? thanks.button_url : undefined} className="public-submit" data-luna-id="thanks.button">{thanks.button_label || "Continuer"}</a>}
      {thanks.action === "redirect" && interactive && <p className="secure-note">Redirection en cours…</p>}
      {legal}
    </div>;
  }

  const body = <>
    <div className="public-brand" data-luna-id="brand"><span>{monogram(company.name)}</span><strong>{company.name}</strong></div>
    <header>
      <p className="eyebrow" data-luna-id="eyebrow">{content.eyebrow}</p>
      <h1 data-luna-id="title">{form.name}</h1>
      <p data-luna-id="description">{form.description}</p>
    </header>
    <div className="public-fields">
      {form.fields.map(field => field.type === "consent" ? (
        <label className="public-consent" key={field.id} data-luna-id={`field:${field.id}`} data-field={field.id}>
          <input type="checkbox" checked={consent} disabled={!interactive} onChange={event => onConsent?.(event.target.checked)}/>
          <span><i><Check size={13}/></i>{field.label}</span>
        </label>
      ) : (
        <RenderedField
          key={field.id}
          field={field}
          value={values[field.id] ?? ""}
          error={errors[field.id]}
          interactive={interactive}
          onChange={value => onChange?.(field.id, value)}
        />
      ))}
    </div>
    {error && <p className="form-error">{error}</p>}
    <button className="public-submit" type={interactive ? "submit" : "button"} disabled={busy} data-luna-id="submit">
      {busy ? "Envoi en cours…" : <>{content.submit_label} <Send size={17}/></>}
    </button>
    <p className="secure-note" data-luna-id="trust">{content.trust_note}</p>
    {legal}
  </>;

  if (interactive) return <form className={cardClass} onSubmit={onSubmit} noValidate data-luna-id="card">{body}</form>;
  return <div className={cardClass} data-luna-id="card">{body}</div>;
}

function RenderedField({ field, value, error, interactive, onChange }: { field: Field; value: string | number; error?: string; interactive: boolean; onChange: (value: string | number) => void }) {
  const label = <>{field.label}{field.required && " *"}</>;
  const hint = error && <span className="field-error">{error}</span>;
  const shared = { "data-luna-id": `field:${field.id}`, "data-field": field.id } as const;

  if (field.type === "rating") return <div className="public-field" {...shared}>
    <label data-luna-id={`field:${field.id}.label`}>{label}</label>
    <div className="public-rating">{Array.from({ length: field.scale || 5 }, (_, index) => index + 1).map(note => (
      <button type="button" key={note} aria-pressed={value === note} className={value === note ? "selected" : ""} onClick={() => interactive && onChange(note)}>{note}</button>
    ))}</div>
    {hint}
  </div>;

  if (field.type === "radio") return <div className="public-field" {...shared}>
    <label data-luna-id={`field:${field.id}.label`}>{label}</label>
    <div className="public-options">{field.options?.map(option => (
      <button type="button" key={option} aria-pressed={value === option} className={value === option ? "selected" : ""} onClick={() => interactive && onChange(option)}>{option}</button>
    ))}</div>
    {hint}
  </div>;

  if (field.type === "select") return <label className="public-field" {...shared}>
    <span data-luna-id={`field:${field.id}.label`}>{label}</span>
    <div className="select-wrap">
      <select value={value} disabled={!interactive} onChange={event => onChange(event.target.value)}>
        <option value="">Sélectionnez une option</option>
        {field.options?.map(option => <option key={option}>{option}</option>)}
      </select>
      <ChevronDown/>
    </div>
    {hint}
  </label>;

  if (field.type === "textarea") return <label className="public-field" {...shared}>
    <span data-luna-id={`field:${field.id}.label`}>{label}</span>
    <textarea value={value} readOnly={!interactive} placeholder={field.placeholder} onChange={event => onChange(event.target.value)}/>
    {hint}
  </label>;

  return <label className="public-field" {...shared}>
    <span data-luna-id={`field:${field.id}.label`}>{label}</span>
    <input type={field.type === "tel" ? "tel" : field.type} value={value} readOnly={!interactive} placeholder={field.placeholder} onChange={event => onChange(event.target.value)}/>
    {hint}
  </label>;
}

/** Enveloppe de page : degrade, police et couleurs du style choisi par Luna. */
export function FormStage({ design, className = "", children, style, as: Tag = "div" }: { design: FormDesign; className?: string; children: React.ReactNode; style?: React.CSSProperties; as?: "div" | "main" | "section" }) {
  return <Tag className={`${backgroundClassName(design)} ${className}`} style={{ ...formStyleVars(design), ...style }}>{children}</Tag>;
}
