"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, Download, Inbox, Search, Trash2, X } from "lucide-react";
import { Badge, EmptyState, ErrorState, Loading } from "@/components/ui";
import { API_URL, api, getToken } from "@/lib/api";
import type { Campaign, Field, Form, ResponsePage, ResponseRow } from "@/lib/types";

const PAGE_SIZE = 25;
const dateTime = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });

type Filters = { campaign_id: string; form_id: string; source: string; from: string; to: string; q: string };

const EMPTY: Filters = { campaign_id: "", form_id: "", source: "", from: "", to: "", q: "" };

function toQuery(filters: Filters, extra: Record<string, string> = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...extra })) if (value) params.set(key, value);
  return params;
}

/**
 * Boite de reception : les reponses de toutes les campagnes, ou d'une seule.
 * Le meme composant sert la page Reponses et l'onglet Reponses d'une campagne.
 */
export function ResponsesInbox({ campaignId, formId }: { campaignId?: string; formId?: string }) {
  const fixed = useMemo(() => ({ campaign_id: campaignId || "", form_id: formId || "" }), [campaignId, formId]);
  const [filters, setFilters] = useState<Filters>({ ...EMPTY, ...fixed });
  const [page, setPage] = useState<ResponsePage | null>(null);
  const [offset, setOffset] = useState(0);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [forms, setForms] = useState<Form[]>([]);
  const [selected, setSelected] = useState<ResponseRow | null>(null);
  const [labels, setLabels] = useState<Record<string, Field[]>>({});
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    setPage(null);
    api<ResponsePage>(`/responses?${toQuery(filters, { limit: String(PAGE_SIZE), offset: String(offset) })}`)
      .then(setPage)
      .catch(err => setError(err instanceof Error ? err.message : "Une erreur est survenue"));
  }, [filters, offset]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (campaignId || formId) return;
    void api<Campaign[]>("/campaigns").then(setCampaigns).catch(() => undefined);
  }, [campaignId, formId]);

  // La liste des formulaires suit la campagne choisie : sans campagne, pas de filtre formulaire.
  useEffect(() => {
    if (!filters.campaign_id || formId) { setForms([]); return; }
    void api<Form[]>(`/campaigns/${filters.campaign_id}/forms`).then(setForms).catch(() => setForms([]));
  }, [filters.campaign_id, formId]);

  // Les libelles viennent du formulaire : une reponse ne stocke que les identifiants de champs.
  useEffect(() => {
    if (!selected || labels[selected.form_id]) return;
    void api<Form>(`/forms/${selected.form_id}`).then(form => setLabels(current => ({ ...current, [form.id]: form.fields }))).catch(() => undefined);
  }, [selected, labels]);

  function update(changes: Partial<Filters>) {
    setOffset(0);
    setSelected(null);
    setFilters(current => ({ ...current, ...changes, ...(changes.campaign_id !== undefined ? { form_id: fixed.form_id } : {}) }));
  }

  const active = useMemo(() => Object.entries(filters).some(([key, value]) => value && value !== fixed[key as keyof typeof fixed]), [filters, fixed]);

  async function exportCsv() {
    try {
      const response = await fetch(`${API_URL}/responses/export.csv?${toQuery(filters)}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!response.ok) throw new Error("Export impossible");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "reponses.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export impossible");
    }
  }

  async function remove(row: ResponseRow) {
    await api(`/responses/${row.id}`, { method: "DELETE" });
    setSelected(null);
    load();
  }

  return <div className="inbox">
    <div className="inbox-filters">
      <div className="search-box"><Search size={18}/><input placeholder="Rechercher dans les réponses…" value={filters.q} onChange={event => update({ q: event.target.value })}/></div>
      {!campaignId && !formId && <select value={filters.campaign_id} onChange={event => update({ campaign_id: event.target.value })} aria-label="Campagne">
        <option value="">Toutes les campagnes</option>
        {campaigns.map(campaign => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
      </select>}
      {!formId && <select value={filters.form_id} onChange={event => update({ form_id: event.target.value })} disabled={!filters.campaign_id} aria-label="Formulaire">
        <option value="">{filters.campaign_id ? "Tous les formulaires" : "Choisissez une campagne"}</option>
        {forms.map(form => <option key={form.id} value={form.id}>{form.name}</option>)}
      </select>}
      <select value={filters.source} onChange={event => update({ source: event.target.value })} aria-label="Source">
        <option value="">Toutes les sources</option>
        {(page?.sources || []).map(source => <option key={source} value={source}>{source}</option>)}
      </select>
      <label className="inbox-date">Du <input type="date" value={filters.from} onChange={event => update({ from: event.target.value })}/></label>
      <label className="inbox-date">Au <input type="date" value={filters.to} min={filters.from || undefined} onChange={event => update({ to: event.target.value })}/></label>
      {active && <button className="text-link" onClick={() => { setOffset(0); setSelected(null); setFilters({ ...EMPTY, ...fixed }); }}>Réinitialiser</button>}
      <span className="inbox-spacer"/>
      <button className="button button-secondary" onClick={() => void exportCsv()} disabled={!page?.total}><Download size={17}/>Exporter CSV</button>
    </div>

    {error ? <ErrorState message={error} onRetry={load}/> : !page ? <Loading/> : page.total === 0 ? (
      <EmptyState icon={<Inbox/>} title={active ? "Aucune réponse pour ces filtres" : "Aucune réponse pour le moment"} text={active ? "Élargissez la période ou retirez un filtre." : "Les réponses arriveront ici dès qu’un formulaire publié sera rempli."}/>
    ) : <>
      <div className="inbox-grid">
        <div className="panel inbox-list">
          <div className="response-table-head"><span>Contact</span><span>Formulaire</span><span>Source</span><span>Reçue le</span></div>
          {page.items.map(row => <button className={`response-table-row ${selected?.id === row.id ? "selected" : ""}`} key={row.id} onClick={() => setSelected(row)}>
            <div><strong>{String(row.answers.name || "Réponse anonyme")}</strong><span>{String(row.answers.email || row.answers.comment || row.answers.message || "—")}</span></div>
            <div><strong>{row.form}</strong><span>{row.campaign}</span></div>
            <Badge>{row.source}</Badge>
            <span>{dateTime.format(new Date(row.created_at))}</span>
          </button>)}
        </div>
        {selected && <ResponseDetail row={selected} fields={labels[selected.form_id]} onClose={() => setSelected(null)} onDelete={() => void remove(selected)}/>}
      </div>
      <div className="inbox-pager">
        <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} sur {page.total}</span>
        <button className="button button-secondary" disabled={offset === 0} onClick={() => { setSelected(null); setOffset(Math.max(0, offset - PAGE_SIZE)); }}>Précédentes</button>
        <button className="button button-secondary" disabled={offset + PAGE_SIZE >= page.total} onClick={() => { setSelected(null); setOffset(offset + PAGE_SIZE); }}>Suivantes</button>
      </div>
    </>}
  </div>;
}

function ResponseDetail({ row, fields, onClose, onDelete }: { row: ResponseRow; fields?: Field[]; onClose: () => void; onDelete: () => void }) {
  const entries = Object.entries(row.answers).filter(([, value]) => value !== "" && value !== null);
  const label = (key: string) => fields?.find(field => field.id === key)?.label || key;
  return <aside className="panel inbox-detail">
    <div className="panel-head">
      <div><p className="eyebrow">RÉPONSE</p><h2>{String(row.answers.name || "Réponse anonyme")}</h2></div>
      <button className="icon-button" onClick={onClose} aria-label="Fermer le détail"><X size={18}/></button>
    </div>
    <p className="inbox-detail-origin"><Link href={`/campaigns/${row.campaign_id}/forms/${row.form_id}`}>{row.form}</Link> · {row.campaign} · {dateTime.format(new Date(row.created_at))}</p>
    <dl className="detail-facts">
      {entries.map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{String(value)}</dd></div>)}
      <div><dt>Source</dt><dd>{row.source}</dd></div>
      {row.promo_code && <div><dt>Code promo</dt><dd>{row.promo_code}</dd></div>}
    </dl>
    <div className="consent-proof">
      <p className="eyebrow">PREUVE DE CONSENTEMENT</p>
      <p className={row.consent ? "consent-ok" : "consent-ko"}>{row.consent ? <><Check size={15}/>Recueilli</> : <><X size={15}/>Non recueilli</>}</p>
      {row.consent_text && <blockquote>{row.consent_text}</blockquote>}
      <small>{row.ip_address || "IP inconnue"} · {row.user_agent || "Navigateur inconnu"}</small>
    </div>
    <button className="button button-secondary inbox-delete" onClick={onDelete}><Trash2 size={16}/>Supprimer cette réponse</button>
  </aside>;
}
