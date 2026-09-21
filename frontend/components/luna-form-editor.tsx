"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, LoaderCircle, Monitor, MousePointer2, Send, Smartphone, Sparkles, Undo2, X } from "lucide-react";
import { FormRenderer, FormStage } from "@/components/form-renderer";
import { useMe } from "@/components/shell";
import { api } from "@/lib/api";
import { captureRegion } from "@/lib/capture";
import type { Campaign, Field, FormContent } from "@/lib/types";

type Version = { id: string; source: string; instruction: string; message: string; created_at: string };
type Rect = { x: number; y: number; width: number; height: number };
type Selection = { rect: Rect; ids: string[]; label: string; dataUrl?: string };

/** Etat edite : le brouillon s'il existe, sinon le formulaire publie. */
function editingState(campaign: Campaign): Campaign {
  return { ...campaign, ...(campaign.draft || {}) };
}

/** Nom lisible d'un element du rendu, pour l'afficher a l'utilisateur. */
function readableName(id: string, fields: Field[]) {
  if (id.startsWith("field:")) {
    const fieldId = id.slice(6).replace(".label", "");
    return fields.find(field => field.id === fieldId)?.label || "un champ";
  }
  return ({
    card: "le formulaire",
    brand: "le logo",
    eyebrow: "le sur-titre",
    title: "le titre",
    description: "la description",
    submit: "le bouton",
    trust: "la note de confiance",
    footer: "le pied de page",
    "thanks.title": "le titre du remerciement",
    "thanks.message": "le message de remerciement",
    "thanks.button": "le bouton du remerciement",
  } as Record<string, string>)[id] || id;
}

function selectionLabel(ids: string[], fields: Field[]) {
  if (!ids.length || ids.includes("card")) return "Formulaire complet";
  const names = [...new Set(ids.map(id => readableName(id, fields)))];
  return names.slice(0, 3).join(", ") + (names.length > 3 ? "…" : "");
}

export function LunaFormEditor({ campaign, onCampaignChange }: { campaign: Campaign; onCampaignChange: (campaign: Campaign) => void }) {
  const me = useMe();
  const [configured, setConfigured] = useState(true);
  const [versions, setVersions] = useState<Version[]>([]);
  const [view, setView] = useState<"form" | "thanks">("form");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [dragRect, setDragRect] = useState<Rect | null>(null);
  const [instruction, setInstruction] = useState("");
  const [pending, setPending] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [touched, setTouched] = useState<string[]>([]);
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  // Le rectangle vit aussi dans une ref : mousemove et mouseup peuvent tomber
  // dans le meme lot de rendu, et l'etat serait alors en retard.
  const dragRectRef = useRef<Rect | null>(null);
  const bubbleRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);

  const draft = editingState(campaign);
  const hasDraft = Boolean(campaign.draft);
  const company = { name: me?.company.name || "Votre entreprise" };

  const loadVersions = useCallback(() => {
    void api<Version[]>(`/campaigns/${campaign.id}/versions`).then(setVersions).catch(() => undefined);
  }, [campaign.id]);

  useEffect(() => { void api<{ configured: boolean }>("/luna/status").then(data => setConfigured(data.configured)).catch(() => undefined); }, []);
  useEffect(() => { loadVersions(); }, [loadVersions]);

  // Conversation reconstituee depuis l'historique : elle suit l'utilisateur
  // d'un appareil a l'autre, et c'est la memoire donnee a Luna.
  const messages = useMemo(() => versions
    .filter(version => version.source === "luna" && version.instruction)
    .flatMap(version => [
      { id: `${version.id}-user`, role: "user" as const, text: version.instruction, versionId: version.id },
      { id: version.id, role: "luna" as const, text: version.message, versionId: version.id },
    ]), [versions]);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!touched.length) return;
    const timer = setTimeout(() => setTouched([]), 1600);
    return () => clearTimeout(timer);
  }, [touched]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") { setSelection(null); setDragRect(null); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function pointIn(event: React.MouseEvent) {
    const bounds = canvasRef.current!.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  }

  function startDrag(event: React.MouseEvent) {
    if (event.button !== 0 || (event.target as HTMLElement).isContentEditable) return;
    dragStart.current = pointIn(event);
    dragRectRef.current = null;
    setSelection(null);
    setDragRect(null);
  }

  function moveDrag(event: React.MouseEvent) {
    if (!dragStart.current) return;
    const current = pointIn(event);
    const rect = {
      x: Math.min(dragStart.current.x, current.x),
      y: Math.min(dragStart.current.y, current.y),
      width: Math.abs(current.x - dragStart.current.x),
      height: Math.abs(current.y - dragStart.current.y),
    };
    dragRectRef.current = rect;
    setDragRect(rect);
  }

  async function endDrag() {
    const rect = dragRectRef.current;
    dragStart.current = null;
    dragRectRef.current = null;
    setDragRect(null);
    if (!rect || rect.width < 12 || rect.height < 12) return; // un simple clic n'est pas une selection

    const canvas = canvasRef.current!;
    const bounds = canvas.getBoundingClientRect();
    const ids: string[] = [];
    canvas.querySelectorAll<HTMLElement>("[data-luna-id]").forEach(element => {
      const box = element.getBoundingClientRect();
      const x = box.left - bounds.left;
      const y = box.top - bounds.top;
      if (x < rect.x + rect.width && x + box.width > rect.x && y < rect.y + rect.height && y + box.height > rect.y) {
        ids.push(element.dataset.lunaId!);
      }
    });
    // La carte entiere ne compte que si rien de plus precis n'est dans le cadre.
    const precise = ids.filter(id => id !== "card");
    const kept = precise.length ? precise : ids;

    setSelection({ rect, ids: kept, label: selectionLabel(kept, draft.fields) });
    setTimeout(() => bubbleRef.current?.focus(), 30);
    try {
      const dataUrl = await captureRegion(canvas, rect);
      setSelection(current => current && { ...current, dataUrl });
    } catch {
      // Sans capture, la demande part quand meme avec les elements encadres.
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = instruction.trim();
    if (!text || busy) return;
    const current = selection;
    setBusy(true);
    setError("");
    setPending(text);
    setInstruction("");
    setSelection(null);
    try {
      const result = await api<{ message: string; campaign: Campaign; touched: string[] }>(`/campaigns/${campaign.id}/luna/refine`, {
        method: "POST",
        body: JSON.stringify({
          instruction: text,
          element_ids: current?.ids || [],
          selection_label: current?.label || "Formulaire complet",
          view,
          screenshot_data_url: current?.dataUrl || null,
        }),
      });
      onCampaignChange(result.campaign);
      setTouched(result.touched);
      loadVersions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Luna n’a pas pu appliquer la modification.");
      setInstruction(text);
    } finally {
      setPending("");
      setBusy(false);
    }
  }

  async function act(path: string) {
    setBusy(true);
    setError("");
    try {
      const updated = await api<Campaign>(`/campaigns/${campaign.id}${path}`, { method: "POST" });
      onCampaignChange(updated);
      loadVersions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action impossible");
    } finally {
      setBusy(false);
    }
  }

  /** Annuler une etape, c'est revenir a la version qui la precede. */
  function undoTo(versionId: string) {
    const index = versions.findIndex(version => version.id === versionId);
    const previous = versions[index - 1];
    if (previous) void act(`/versions/${previous.id}/restore`);
  }

  async function saveText(lunaId: string, value: string) {
    let body: Record<string, unknown> | null = null;
    if (lunaId === "title") body = { name: value };
    else if (lunaId === "description") body = { description: value };
    else if (["eyebrow", "submit", "trust"].includes(lunaId)) {
      const key = ({ eyebrow: "eyebrow", submit: "submit_label", trust: "trust_note" } as Record<string, keyof FormContent>)[lunaId];
      body = { content: { ...draft.content, [key]: value } };
    } else if (lunaId.startsWith("field:") && lunaId.endsWith(".label")) {
      const fieldId = lunaId.slice(6, -6);
      body = { fields: draft.fields.map(field => field.id === fieldId ? { ...field, label: value } : field) };
    }
    if (!body) return;
    try {
      const updated = await api<Campaign>(`/campaigns/${campaign.id}/draft`, { method: "PATCH", body: JSON.stringify(body) });
      onCampaignChange(updated);
      loadVersions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Modification impossible");
    }
  }

  /** Double-clic : corriger un texte a la main, sans passer par Luna. */
  function editText(event: React.MouseEvent) {
    const element = (event.target as HTMLElement).closest<HTMLElement>("[data-luna-id]");
    const lunaId = element?.dataset.lunaId;
    if (!element || !lunaId) return;
    if (!["title", "description", "eyebrow", "submit", "trust"].includes(lunaId) && !lunaId.endsWith(".label")) return;
    event.preventDefault();
    const original = element.textContent || "";
    element.contentEditable = "true";
    element.classList.add("inline-editing");
    element.focus();

    const finish = (save: boolean) => {
      element.removeEventListener("blur", onBlur);
      element.removeEventListener("keydown", onKeyDown);
      element.contentEditable = "false";
      element.classList.remove("inline-editing");
      const value = (element.textContent || "").trim();
      if (save && value && value !== original) void saveText(lunaId, value);
      else element.textContent = original;
    };
    const onBlur = () => finish(true);
    const onKeyDown = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === "Enter") { keyEvent.preventDefault(); finish(true); }
      if (keyEvent.key === "Escape") { keyEvent.preventDefault(); finish(false); }
    };
    element.addEventListener("blur", onBlur);
    element.addEventListener("keydown", onKeyDown);
  }

  return <div className="luna-editor">
    <div className="editor-bar">
      <span className={`draft-state ${hasDraft ? "pending" : ""}`}>{hasDraft ? "Brouillon non publié" : "À jour avec le formulaire en ligne"}</span>
      <div className="segment-control">
        <button className={view === "form" ? "selected" : ""} onClick={() => setView("form")}>Formulaire</button>
        <button className={view === "thanks" ? "selected" : ""} onClick={() => setView("thanks")}>Remerciement</button>
      </div>
      <div className="segment-control">
        <button className={device === "desktop" ? "selected" : ""} onClick={() => setDevice("desktop")} aria-label="Aperçu ordinateur"><Monitor size={16}/></button>
        <button className={device === "mobile" ? "selected" : ""} onClick={() => setDevice("mobile")} aria-label="Aperçu mobile"><Smartphone size={16}/></button>
      </div>
      <span className="editor-bar-spacer"/>
      {hasDraft && <button className="button button-secondary" onClick={() => void act("/draft/discard")} disabled={busy}><X size={16}/>Abandonner</button>}
      <button className="button button-primary" onClick={() => void act("/draft/publish")} disabled={!hasDraft || busy}><Check size={16}/>Publier les modifications</button>
    </div>

    <div className="editor-columns">
      <section className="editor-preview-panel">
        <p className="editor-hint"><MousePointer2 size={15}/>Encadrez une zone à la souris pour demander une modification. Double-cliquez un texte pour le corriger vous-même.</p>
        <FormStage design={draft.design} className={`editor-canvas device-${device}`}>
          <div
            ref={canvasRef}
            className="editor-selection-layer"
            onMouseDown={startDrag}
            onMouseMove={moveDrag}
            onMouseUp={() => void endDrag()}
            onDoubleClick={editText}
          >
            <div className="editor-form-frame">
              <FormRenderer form={draft} company={company} mode="edit" view={view}/>
            </div>
            {touched.map(id => <TouchedHalo key={id} lunaId={id} canvas={canvasRef.current}/>)}
            {dragRect && <div className="selection-rect" style={{ left: dragRect.x, top: dragRect.y, width: dragRect.width, height: dragRect.height }}/>}
            {selection && <>
              <div className="selection-rect kept" style={{ left: selection.rect.x, top: selection.rect.y, width: selection.rect.width, height: selection.rect.height }}/>
              <form className="selection-bubble" style={{ left: selection.rect.x, top: selection.rect.y + selection.rect.height + 10 }} onSubmit={send} onMouseDown={event => event.stopPropagation()}>
                <span>{selection.label}</span>
                <textarea ref={bubbleRef} value={instruction} maxLength={800} placeholder="Que voulez-vous changer ici ?" onChange={event => setInstruction(event.target.value)} disabled={!configured || busy}/>
                <div>
                  <button type="button" onClick={() => setSelection(null)}>Annuler</button>
                  <button className="button button-primary" disabled={!instruction.trim() || !configured || busy}>{busy ? <LoaderCircle className="spin" size={15}/> : <Send size={15}/>}Envoyer</button>
                </div>
              </form>
            </>}
          </div>
        </FormStage>
      </section>

      <aside className="luna-chat-panel">
        <header className="luna-chat-head">
          <div className="luna-chat-avatar"><Sparkles size={18}/></div>
          <div><strong>Luna</strong><span>{configured ? "Connectée" : "Indisponible"}</span></div>
          <i className={configured ? "online" : ""}/>
        </header>
        <div className="luna-chat-messages" ref={messagesRef}>
          {!messages.length && <div className="chat-message assistant"><p>Encadrez une zone du formulaire, ou écrivez directement ce que vous souhaitez changer.</p></div>}
          {messages.map(message => <div className={`chat-message ${message.role === "luna" ? "assistant" : "user"}`} key={message.id}>
            <p>{message.text}</p>
            {message.role === "luna" && <button className="chat-undo" onClick={() => undoTo(message.versionId)} disabled={busy}><Undo2 size={13}/>Annuler cette modification</button>}
          </div>)}
          {pending && <div className="chat-message user"><p>{pending}</p></div>}
          {busy && <div className="chat-message assistant thinking"><span/><span/><span/></div>}
          {error && <div className="chat-message assistant error"><p>{error}</p></div>}
        </div>
        <form className="luna-chat-composer" onSubmit={send}>
          <textarea value={instruction} maxLength={800} placeholder="Ex. Rends le bouton plus visible…" onChange={event => setInstruction(event.target.value)} disabled={!configured || busy}/>
          <div className="composer-actions">
            <span className="composer-target">{selection ? selection.label : "Formulaire complet"}</span>
            <button className="chat-send" disabled={!instruction.trim() || !configured || busy} aria-label="Envoyer à Luna"><Send size={17}/></button>
          </div>
          {!configured && <p className="composer-help">Luna n’est pas connectée. Un administrateur doit renseigner la clé du service d’IA.</p>}
        </form>
      </aside>
    </div>
  </div>;
}

/** Halo bref sur un element que Luna vient de modifier. */
function TouchedHalo({ lunaId, canvas }: { lunaId: string; canvas: HTMLElement | null }) {
  const element = canvas?.querySelector<HTMLElement>(`[data-luna-id="${CSS.escape(lunaId)}"]`);
  if (!canvas || !element) return null;
  const bounds = canvas.getBoundingClientRect();
  const box = element.getBoundingClientRect();
  return <div className="touched-halo" style={{ left: box.left - bounds.left - 6, top: box.top - bounds.top - 6, width: box.width + 12, height: box.height + 12 }}/>;
}
