"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Bookmark, Check, ChevronDown, Clock3, FileText, LayoutTemplate, LoaderCircle, Plus, Search, Send, Sparkles, Star, TrendingUp, X } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { backgroundClassName, designClassNames, formStyleVars } from "@/lib/form-design";
import type { Campaign, Field, LibraryData, LibraryTemplate } from "@/lib/types";

const categories = ["Tous", "Contact", "Sondage", "Information"];

export default function LibraryPage() {
  const router = useRouter();
  const carouselRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<LibraryData | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Tous");
  const [selected, setSelected] = useState<LibraryTemplate | null>(null);
  const [busyAction, setBusyAction] = useState<{ key: string; action: string } | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => { void api<LibraryData>("/library").then(setData); }, []);
  useEffect(() => {
    if (!selected) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setSelected(null); };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [selected]);

  const matches = (template: LibraryTemplate) => {
    const search = query.trim().toLocaleLowerCase("fr");
    return (category === "Tous" || template.category === category) &&
      (!search || `${template.name} ${template.category} ${template.description}`.toLocaleLowerCase("fr").includes(search));
  };
  const featured = useMemo(() => data?.featured.filter(matches) || [], [data, query, category]);
  const saved = useMemo(() => data?.saved.filter(matches) || [], [data, query, category]);
  const recent = useMemo(() => data?.recent.filter(campaign => {
    const search = query.trim().toLocaleLowerCase("fr");
    const campaignCategory = categoryLabel(campaign.kind);
    return (category === "Tous" || campaignCategory === category) &&
      (!search || `${campaign.name} ${campaign.description} ${campaignCategory}`.toLocaleLowerCase("fr").includes(search));
  }) || [], [data, query, category]);

  function scrollCarousel(direction: number) {
    carouselRef.current?.scrollBy({ left: direction * 370, behavior: "smooth" });
  }

  async function saveTemplate(template: LibraryTemplate) {
    setBusyAction({ key: template.key, action: "save" });
    try {
      const item = await api<LibraryTemplate>(`/library/featured/${template.key}/save`, { method: "POST" });
      setData(current => current ? { ...current, saved: [item, ...current.saved.filter(savedItem => savedItem.id !== item.id)] } : current);
      setSelected(current => current?.key === item.key ? item : current);
      setNotice("Ajouté à vos modèles");
      setTimeout(() => setNotice(""), 2200);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Ajout impossible");
      setTimeout(() => setNotice(""), 2600);
    } finally {
      setBusyAction(null);
    }
  }

  async function useTemplate(template: LibraryTemplate) {
    setBusyAction({ key: template.id || template.key, action: "use" });
    try {
      const path = template.id ? `/library/templates/${template.id}/use` : `/library/featured/${template.key}/use`;
      const campaign = await api<Campaign>(path, { method: "POST" });
      router.push(`/campaigns/${campaign.id}?tab=form`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Création impossible");
      setTimeout(() => setNotice(""), 2600);
    } finally {
      setBusyAction(null);
    }
  }

  return <div className="page-wrap library-page">
    <PageHeader eyebrow="INSPIRATION & MODÈLES" title="Bibliothèque" description="Trouvez une base solide, prévisualisez-la, puis adaptez-la à votre marque avec Luna." actions={<Link href="/campaigns/new" className="button button-primary"><Sparkles size={17}/>Créer avec Luna</Link>}/>

    <div className="library-commandbar">
      <div className="library-search search-box"><Search size={18}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Rechercher un modèle…"/></div>
      <div className="library-filters" aria-label="Filtrer par catégorie">{categories.map(item => <button className={category === item ? "active" : ""} onClick={() => setCategory(item)} key={item}>{item}</button>)}</div>
    </div>

    {!data ? <Loading/> : <>
      <section className="library-section library-featured" id="popular">
        <div className="library-section-head">
          <div><span className="section-kicker"><TrendingUp size={14}/>Sélection</span><h2>Modèles Sillage</h2><p>Des bases prêtes à l’emploi pour les besoins les plus courants.</p></div>
          <div className="carousel-controls"><button onClick={() => scrollCarousel(-1)} aria-label="Précédent"><ArrowLeft/></button><button onClick={() => scrollCarousel(1)} aria-label="Suivant"><ArrowRight/></button></div>
        </div>
        {featured.length ? <div className="template-carousel" ref={carouselRef}>{featured.map((template, index) => <TemplateCard template={template} rank={index + 1} onOpen={setSelected} key={template.key}/>)}</div> : <NoResult/>}
      </section>

      <section className="library-section">
        <div className="library-section-head">
          <div><span className="section-kicker"><Bookmark size={14}/>Votre espace</span><h2>Mes modèles <small>{saved.length}</small></h2><p>Vos bases enregistrées, prêtes à être réutilisées sans toucher à l’original.</p></div>
        </div>
        {saved.length ? <div className="saved-template-grid">{saved.map(template => <SavedTemplateCard template={template} onOpen={setSelected} onUse={useTemplate} busy={busyAction?.key === template.id && busyAction?.action === "use"} key={template.id}/>)}</div> : <div className="library-empty">
          <div><LayoutTemplate/></div><h3>Votre collection commence ici</h3><p>Ajoutez un modèle populaire pour le retrouver et le réutiliser à tout moment.</p><button className="text-link" onClick={() => document.getElementById("popular")?.scrollIntoView({ behavior: "smooth" })}>Explorer les modèles <ArrowRight size={15}/></button>
        </div>}
      </section>

      <section className="library-section library-recent">
        <div className="library-section-head">
          <div><span className="section-kicker"><Clock3 size={14}/>Activité</span><h2>Récemment utilisés</h2><p>Reprenez rapidement vos derniers formulaires.</p></div>
          <Link href="/campaigns" className="text-link">Toutes les campagnes <ArrowRight size={15}/></Link>
        </div>
        {recent.length ? <div className="recent-template-list">{recent.map(campaign => <RecentCampaign campaign={campaign} key={campaign.id}/>)}</div> : <NoResult/>}
      </section>
    </>}

    {selected && <TemplateModal template={selected} saved={Boolean(selected.id)} busyAction={busyAction?.action || ""} onClose={() => setSelected(null)} onSave={saveTemplate} onUse={useTemplate}/>}
    {notice && <div className="library-toast"><Check size={16}/>{notice}</div>}
  </div>;
}

function TemplateCard({ template, rank, onOpen }: { template: LibraryTemplate; rank: number; onOpen: (template: LibraryTemplate) => void }) {
  return <button className="template-showcase-card" onClick={() => onOpen(template)}>
    <div className="template-rank">0{rank}</div>
    <TemplateMiniature template={template}/>
    <div className="template-card-copy"><div><span>{template.category}</span><small><Star size={12}/>Sélection Sillage</small></div><h3>{template.name}</h3><p>{template.description}</p><footer><span>{template.field_count} champs · {template.minutes} min</span><i><ArrowRight size={16}/></i></footer></div>
  </button>;
}

function SavedTemplateCard({ template, onOpen, onUse, busy }: { template: LibraryTemplate; onOpen: (template: LibraryTemplate) => void; onUse: (template: LibraryTemplate) => void; busy: boolean }) {
  return <article className="saved-template-card panel">
    <button className="saved-template-preview" onClick={() => onOpen(template)}><TemplateMiniature template={template}/></button>
    <div className="saved-template-copy"><span>{template.category}</span><h3>{template.name}</h3><p>{template.field_count} champs · utilisé {template.uses || 0} fois</p><div><button className="button button-secondary" onClick={() => onOpen(template)}>Aperçu</button><button className="button button-primary" onClick={() => void onUse(template)} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16}/> : <Plus size={16}/>}Utiliser</button></div></div>
  </article>;
}

function RecentCampaign({ campaign }: { campaign: Campaign }) {
  return <Link href={`/campaigns/${campaign.id}?tab=form`} className="recent-template-row">
    <div className={`recent-template-visual ${backgroundClassName(campaign.design)}`} style={formStyleVars(campaign.design)}><div className={designClassNames(campaign.design)}><span/><span/><span/></div></div>
    <div><span>{categoryLabel(campaign.kind)}</span><strong>{campaign.name}</strong><small>Modifié {relativeDate(campaign.updated_at)}</small></div>
    <div className="recent-template-stats"><strong>{campaign.responses}</strong><span>réponses</span></div>
    <ArrowRight size={18}/>
  </Link>;
}

function TemplateMiniature({ template }: { template: LibraryTemplate }) {
  const style = { ...formStyleVars(template.design), "--template-accent": template.accent || "#2F6B4F" } as React.CSSProperties;
  return <div className={`template-miniature ${backgroundClassName(template.design)}`} style={style}>
    <div className={`template-mini-card ${designClassNames(template.design)}`}>
      <div className="mini-brand"><i/><span>{template.category}</span></div><strong>{template.name}</strong><p>{template.description}</p>
      <div className="mini-fields">{template.fields.slice(0, 3).map(field => <span className={field.type === "textarea" ? "tall" : ""} key={field.id}><i/></span>)}</div>
      <span className="mini-submit">Continuer</span>
    </div>
  </div>;
}

function TemplateModal({ template, saved, busyAction, onClose, onSave, onUse }: { template: LibraryTemplate; saved: boolean; busyAction: string; onClose: () => void; onSave: (template: LibraryTemplate) => void; onUse: (template: LibraryTemplate) => void }) {
  const style = { ...formStyleVars(template.design), "--client": template.accent || "#2F6B4F" } as React.CSSProperties;
  return <div className="template-modal-backdrop" onMouseDown={event => { if (event.currentTarget === event.target) onClose(); }}>
    <div className="template-modal" role="dialog" aria-modal="true" aria-label={`Aperçu de ${template.name}`}>
      <button className="template-modal-close" onClick={onClose} aria-label="Fermer"><X/></button>
      <div className={`template-modal-preview ${backgroundClassName(template.design)}`} style={style}>
        <div className={`template-full-form ${designClassNames(template.design)}`}>
          <div className="template-preview-brand"><i/><span>Votre entreprise</span></div>
          <header><p className="eyebrow">{template.category}</p><h2>{template.name}</h2><p>{template.description}</p></header>
          <div className="template-preview-fields">{template.fields.map(field => <TemplatePreviewField field={field} key={field.id}/>)}</div>
          <button>Envoyer ma réponse <Send size={15}/></button>
        </div>
      </div>
      <aside className="template-modal-copy">
        <span className="section-kicker">{saved ? <Bookmark size={14}/> : <TrendingUp size={14}/>}{saved ? "Votre modèle" : "Modèle Sillage"}</span>
        <h2>{template.name}</h2><p>{template.description}</p>
        <div className="template-modal-meta"><span><FileText/> {template.field_count} champs</span>{template.minutes && <span><Clock3/> {template.minutes} min</span>}<span><Sparkles/> Personnalisable avec Luna</span></div>
        <div className="template-modal-actions">
          {!saved && <button className="button button-secondary" onClick={() => void onSave(template)} disabled={Boolean(busyAction)}>{busyAction === "save" ? <LoaderCircle className="spin" size={16}/> : <Bookmark size={16}/>}Ajouter à mes modèles</button>}
          <button className="button button-primary" onClick={() => void onUse(template)} disabled={Boolean(busyAction)}>{busyAction === "use" ? <LoaderCircle className="spin" size={16}/> : <Plus size={16}/>}Créer ce formulaire</button>
        </div>
        <small>Une nouvelle campagne indépendante sera créée : vous pourrez tout modifier sans altérer ce modèle.</small>
      </aside>
    </div>
  </div>;
}

function TemplatePreviewField({ field }: { field: Field }) {
  if (field.type === "rating") return <div className="template-preview-field"><label>{field.label}</label><div className="template-preview-rating">{[1,2,3,4,5].map(value => <span key={value}>{value}</span>)}</div></div>;
  if (field.type === "radio") return <div className="template-preview-field"><label>{field.label}</label><div className="template-preview-options">{field.options?.map(option => <span key={option}>{option}</span>)}</div></div>;
  return <div className="template-preview-field"><label>{field.label}{field.required && " *"}</label><div className={field.type === "textarea" ? "tall" : ""}>{field.placeholder}</div>{field.type === "select" && <ChevronDown size={15}/>}</div>;
}

function NoResult() { return <div className="library-no-result"><Search/><p>Aucun modèle ne correspond à cette recherche.</p></div>; }
function categoryLabel(kind: string) { return ({ contact: "Contact", survey: "Sondage", information: "Information" } as Record<string, string>)[kind] || "Contact"; }
function relativeDate(date: string) { const days = Math.floor((Date.now() - new Date(date).getTime()) / 86400000); if (days < 1) return "aujourd’hui"; if (days === 1) return "hier"; return `il y a ${days} jours`; }
