"use client";

import { FormEvent, useEffect, useState } from "react";
import { Building2, Check, ImagePlus, Palette, Save, ShieldCheck, Sparkles, Trash2, X } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { ErrorState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { readImageAsDataUrl } from "@/lib/image";
import type { BrandProfile, Me } from "@/lib/types";

const FONTS = [
  { value: "sans", label: "Sans serif moderne" },
  { value: "grotesk", label: "Grotesque" },
  { value: "serif", label: "Serif classique" },
  { value: "mono", label: "Monospace" },
];

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<"company" | "brand">("company");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const load = () => {
    setLoadError("");
    api<Me>("/me").then(setMe).catch(err => setLoadError(err instanceof Error ? err.message : "Une erreur est survenue"));
  };
  useEffect(() => { load(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!me) return;
    setError("");
    try {
      const updated = await api<Me>("/company", { method: "PATCH", body: JSON.stringify(me.company) });
      setMe(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 1600);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enregistrement impossible");
    }
  }

  if (loadError) return <div className="page-wrap settings-page"><ErrorState message={loadError} onRetry={load}/></div>;
  if (!me) return <Loading/>;

  const set = (key: string, value: unknown) => setMe({ ...me, company: { ...me.company, [key]: value } });
  // Une entreprise creee avant le profil de marque n'a pas encore ce bloc.
  const brand: BrandProfile = me.company.brand || {};
  const setBrand = (key: keyof BrandProfile, value: unknown) => set("brand", { ...brand, [key]: value });

  return <div className="page-wrap settings-page">
    <PageHeader eyebrow="IDENTITÉ CLIENT" title="Paramètres" description="Ces informations personnalisent chaque campagne, ses mentions légales et le travail de Luna."/>
    <div className="segment-control settings-tabs">
      <button className={tab === "company" ? "selected" : ""} onClick={() => setTab("company")}>Entreprise</button>
      <button className={tab === "brand" ? "selected" : ""} onClick={() => setTab("brand")}>Profil de marque</button>
    </div>

    <form onSubmit={submit}>
      {tab === "company" ? <>
        <section className="panel settings-section">
          <div className="settings-heading"><div className="metric-icon"><Building2/></div><div><h2>Entreprise</h2><p>Les informations visibles sur vos formulaires.</p></div></div>
          <div className="form-grid">
            <label>Nom commercial<input value={me.company.name} onChange={event => set("name", event.target.value)}/></label>
            <label>Secteur d’activité<input value={me.company.sector} onChange={event => set("sector", event.target.value)}/></label>
            <label>Nom légal<input value={me.company.legal_name} onChange={event => set("legal_name", event.target.value)}/></label>
            <label>Numéro SIRET<input value={me.company.siret} onChange={event => set("siret", event.target.value)}/></label>
            <label className="full">Adresse postale<input value={me.company.address} onChange={event => set("address", event.target.value)}/></label>
          </div>
        </section>
        <section className="panel settings-section">
          <div className="settings-heading"><div className="metric-icon"><ShieldCheck/></div><div><h2>Confidentialité & RGPD</h2><p>Le contact de référence pour les demandes liées aux données.</p></div></div>
          <div className="form-grid"><label>Email DPO<input type="email" value={me.company.dpo_email} onChange={event => set("dpo_email", event.target.value)}/></label></div>
        </section>
      </> : <>
        <section className="panel settings-section">
          <div className="settings-heading"><div className="metric-icon"><Palette/></div><div><h2>Identité visuelle</h2><p>Le point de départ de Luna pour chaque formulaire.</p></div></div>
          <LogoField value={me.company.logo} onChange={value => set("logo", value)} onError={setError}/>
          <div className="color-grid">
            <label>Couleur principale<div className="color-field"><input type="color" value={me.company.primary_color} onChange={event => set("primary_color", event.target.value)}/><input value={me.company.primary_color} onChange={event => set("primary_color", event.target.value)}/></div></label>
            <label>Couleur d’accent<div className="color-field"><input type="color" value={me.company.accent_color} onChange={event => set("accent_color", event.target.value)}/><input value={me.company.accent_color} onChange={event => set("accent_color", event.target.value)}/></div></label>
            <label>Ton de voix<select value={me.company.tone} onChange={event => set("tone", event.target.value)}><option>Professionnel</option><option>Décontracté</option><option>Premium</option><option>Chaleureux</option><option>Direct</option></select></label>
          </div>
        </section>

        <section className="panel settings-section">
          <div className="settings-heading"><div className="metric-icon"><Sparkles/></div><div><h2>Charte graphique</h2><p>Déposez votre charte : Luna en tire un profil que vous validez. Les fichiers ne sont pas conservés.</p></div></div>
          <BrandImport onApply={profile => set("brand", profile)} onError={setError}/>

          <div className="brand-grid">
            <label>Palette
              <PaletteField value={brand.palette || []} onChange={palette => setBrand("palette", palette)}/>
            </label>
            <label>Police proche
              <select value={brand.font || "sans"} onChange={event => setBrand("font", event.target.value)}>{FONTS.map(font => <option key={font.value} value={font.value}>{font.label}</option>)}</select>
            </label>
            <label className="full">Ton en quelques mots<input value={brand.tone || ""} placeholder="Ex. chaleureux et direct" onChange={event => setBrand("tone", event.target.value)}/></label>
            <label className="full">À faire<RuleList value={brand.rules_do || []} placeholder="Ex. garder des phrases courtes" onChange={rules => setBrand("rules_do", rules)}/></label>
            <label className="full">À éviter<RuleList value={brand.rules_avoid || []} placeholder="Ex. ne jamais utiliser de rouge vif" onChange={rules => setBrand("rules_avoid", rules)}/></label>
          </div>
        </section>
      </>}

      {error && <p className="form-error">{error}</p>}
      <div className="save-bar">
        <span>{saved && <><Check size={17}/>Modifications enregistrées</>}</span>
        <button className="button button-primary">{saved ? <Check size={17}/> : <Save size={17}/>}Enregistrer</button>
      </div>
    </form>
  </div>;
}

function LogoField({ value, onChange, onError }: { value: string; onChange: (value: string) => void; onError: (message: string) => void }) {
  async function pick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      onChange(await readImageAsDataUrl(file, 320));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Image illisible");
    }
  }

  return <div className="logo-field">
    <div className="logo-preview">{value ? <img src={value} alt="Logo de l’entreprise"/> : <ImagePlus size={22}/>}</div>
    <div>
      <strong>Logo</strong>
      <p className="muted">PNG, JPEG ou WebP. Il remplace le monogramme sur vos formulaires.</p>
      <div className="logo-actions">
        <label className="button button-secondary">Choisir une image<input type="file" accept="image/png,image/jpeg,image/webp" onChange={pick} hidden/></label>
        {value && <button type="button" className="text-link" onClick={() => onChange("")}><Trash2 size={14}/>Retirer</button>}
      </div>
    </div>
  </div>;
}

function BrandImport({ onApply, onError }: { onApply: (profile: BrandProfile) => void; onError: (message: string) => void }) {
  const [images, setImages] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<BrandProfile | null>(null);

  async function add(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    try {
      const added = await Promise.all(files.slice(0, 4 - images.length).map(file => readImageAsDataUrl(file, 1400)));
      setImages(current => [...current, ...added].slice(0, 4));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Image illisible");
    }
  }

  async function analyze() {
    setBusy(true);
    onError("");
    try {
      setProposal(await api<BrandProfile>("/company/brand/analyze", { method: "POST", body: JSON.stringify({ images, notes }) }));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Analyse impossible");
    } finally {
      setBusy(false);
    }
  }

  return <div className="brand-import">
    <div className="brand-dropzone">
      {images.map((image, index) => <div className="brand-thumb" key={image.slice(-24)}>
        <img src={image} alt={`Page de charte ${index + 1}`}/>
        <button type="button" onClick={() => setImages(current => current.filter((_, position) => position !== index))} aria-label="Retirer cette image"><X size={13}/></button>
      </div>)}
      {images.length < 4 && <label className="brand-add">
        <ImagePlus size={18}/><span>Ajouter une image</span>
        <input type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={add} hidden/>
      </label>}
    </div>
    <p className="field-hint">Logo, page de charte ou capture de votre site. Pour un PDF, exportez les pages en images. Ces images sont envoyées à Luna pour l’analyse, puis oubliées.</p>
    <input value={notes} placeholder="Précision utile : « la couleur secondaire est réservée aux titres »" onChange={event => setNotes(event.target.value)}/>
    <button type="button" className="button button-secondary" disabled={!images.length || busy} onClick={() => void analyze()}><Sparkles size={16}/>{busy ? "Luna lit votre charte…" : "Analyser avec Luna"}</button>

    {proposal && <div className="brand-proposal">
      <strong>Proposition de Luna</strong>
      <p>{proposal.summary}</p>
      <div className="palette-row">{(proposal.palette || []).map(color => <span key={color} style={{ background: color }} title={color}/>)}</div>
      <p className="muted">Ton : {proposal.tone} · Police : {proposal.font}</p>
      <div className="brand-proposal-actions">
        <button type="button" className="text-link" onClick={() => setProposal(null)}>Ignorer</button>
        <button type="button" className="button button-primary" onClick={() => { onApply(proposal); setProposal(null); }}><Check size={15}/>Appliquer ce profil</button>
      </div>
    </div>}
  </div>;
}

function PaletteField({ value, onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  return <div className="palette-field">
    {value.map((color, index) => <span className="palette-chip" key={`${color}-${index}`}>
      <input type="color" value={color} onChange={event => onChange(value.map((item, position) => position === index ? event.target.value : item))}/>
      <button type="button" onClick={() => onChange(value.filter((_, position) => position !== index))} aria-label={`Retirer ${color}`}><X size={12}/></button>
    </span>)}
    {value.length < 6 && <button type="button" className="palette-add" onClick={() => onChange([...value, "#2F6B4F"])}>+ Couleur</button>}
  </div>;
}

function RuleList({ value, placeholder, onChange }: { value: string[]; placeholder: string; onChange: (value: string[]) => void }) {
  return <div className="rule-list">
    {value.map((rule, index) => <div key={index}>
      <input value={rule} onChange={event => onChange(value.map((item, position) => position === index ? event.target.value : item))}/>
      <button type="button" className="icon-button" onClick={() => onChange(value.filter((_, position) => position !== index))} aria-label="Retirer cette règle"><Trash2 size={15}/></button>
    </div>)}
    {value.length < 5 && <button type="button" className="text-link" onClick={() => onChange([...value, ""])}>+ Ajouter une règle</button>}
    {!value.length && <p className="field-hint">{placeholder}</p>}
  </div>;
}
