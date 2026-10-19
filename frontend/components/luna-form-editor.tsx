"use client";

import { FormEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, ImagePlus, LoaderCircle, Monitor, MousePointer2, Send, Smartphone, Sparkles, Undo2, X } from "lucide-react";
import { PageFrame } from "@/components/page-frame";
import { API_URL, api, getToken } from "@/lib/api";
import { captureRegion } from "@/lib/capture";
import { readImageAsDataUrl } from "@/lib/image";
import type { Form, TunnelPage } from "@/lib/types";

type Version = {
  id: string; source: string; instruction: string; message: string; created_at: string;
  screenshot_data_url: string | null; images: string[]; restored_to_version_id: string | null; page_id: string | null;
};
type Rect = { x: number; y: number; width: number; height: number };
type Selection = {
  key: number; rect: Rect; percentRect: Rect; ids: string[]; label: string;
  dataUrl?: string; capturing: boolean;
};

/** Etat edite : le brouillon s'il existe, sinon le formulaire publie. */
function editingState(form: Form): Form {
  return { ...form, ...(form.draft || {}) };
}
/**
 * Elements reellement vises par le cadre.
 *
 * Un simple croisement ne suffit pas : encadrer le titre touchait aussi le
 * logo et la carte entiere. On ne garde donc qu'un element majoritairement
 * couvert par le cadre, et on ecarte ses conteneurs des qu'un element plus
 * precis est retenu.
 */
function elementsInside(canvas: HTMLElement, rect: Rect, frame: HTMLIFrameElement): string[] {
  const bounds = canvas.getBoundingClientRect();
  const frameBounds = frame.getBoundingClientRect();
  const candidates: { id: string; element: HTMLElement; area: number }[] = [];

  frame.contentDocument?.querySelectorAll<HTMLElement>("[data-sillage-region]").forEach(element => {
    const box = element.getBoundingClientRect();
    const x = box.left + (frameBounds?.left || 0) - bounds.left;
    const y = box.top + (frameBounds?.top || 0) - bounds.top;
    const overlap = Math.max(0, Math.min(x + box.width, rect.x + rect.width) - Math.max(x, rect.x))
      * Math.max(0, Math.min(y + box.height, rect.y + rect.height) - Math.max(y, rect.y));
    const area = box.width * box.height;
    if (!area) return;
    // Retenu si le cadre couvre l'essentiel de l'element, ou si l'element
    // occupe a lui seul l'essentiel du cadre (cas d'un clic serre a l'interieur).
    const covered = overlap / area;
    const fills = overlap / Math.max(1, rect.width * rect.height);
    if (covered >= 0.6 || (fills >= 0.75 && covered >= 0.25)) candidates.push({ id: element.dataset.sillageRegion!, element, area });
  });

  if (!candidates.length) return [];
  const precise = candidates.filter(candidate =>
    !candidates.some(other => other !== candidate && candidate.element.contains(other.element)),
  );
  const kept = (precise.length ? precise : candidates).sort((a, b) => a.area - b.area);
  return [...new Set(kept.map(candidate => candidate.id))];
}

export function LunaFormEditor({ form, onFormChange, targetPage, onTargetPageChange }: { form: Form; onFormChange: (form: Form) => void; targetPage?: TunnelPage | null; onTargetPageChange?: (pageId: string) => Promise<void> }) {
  const [configured, setConfigured] = useState(true);
  const [versions, setVersions] = useState<Version[]>([]);
  const [view, setView] = useState<"form" | "thanks">("form");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [dragRect, setDragRect] = useState<Rect | null>(null);
  const [bubblePosition, setBubblePosition] = useState<{ left: number; top: number } | null>(null);
  const [instruction, setInstruction] = useState("");
  const [pending, setPending] = useState<{ text: string; screenshot: string | null; images: string[] } | null>(null);
  const [zoneInstruction, setZoneInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progressiveHtml, setProgressiveHtml] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<string[]>([]);
  const [zoneAttachments, setZoneAttachments] = useState<string[]>([]);
  const canvasRef = useRef<HTMLDivElement>(null);
  const pageFrameRef = useRef<HTMLIFrameElement | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const dragPointer = useRef<{ element: Element; id: number } | null>(null);
  // Le rectangle vit aussi dans une ref : mousemove et mouseup peuvent tomber
  // dans le meme lot de rendu, et l'etat serait alors en retard.
  const dragRectRef = useRef<Rect | null>(null);
  const selectionKey = useRef(0);
  const bubbleRef = useRef<HTMLTextAreaElement>(null);
  const bubbleBoxRef = useRef<HTMLFormElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const lastPreviewAt = useRef(0);

  const draft = editingState(form);
  const pageHtml = progressiveHtml ?? (targetPage?.html ?? (view === "form" ? (draft.draft_html ?? draft.html) : draft.thanks_html));
  const hasDraft = Boolean(form.draft);

  const loadVersions = useCallback(() => {
    void api<Version[]>(`/forms/${form.id}/versions`).then(setVersions).catch(() => undefined);
  }, [form.id]);

  useEffect(() => { void api<{ configured: boolean }>("/luna/status").then(data => setConfigured(data.configured)).catch(() => undefined); }, []);
  useEffect(() => { loadVersions(); }, [loadVersions]);

  const visibleVersions = useMemo(() => targetPage ? versions.filter(version => version.page_id === targetPage.id) : versions, [versions, targetPage]);

  // Conversation reconstituee depuis l'historique : elle suit l'utilisateur
  // d'un appareil a l'autre, et c'est la memoire donnee a Luna.
  const messages = useMemo(() => {
    const cancelled = new Set<string>();
    visibleVersions.forEach((version, restoreIndex) => {
      if (version.source !== "restore" || !version.restored_to_version_id) return;
      const targetIndex = visibleVersions.findIndex(item => item.id === version.restored_to_version_id);
      if (targetIndex < 0 || targetIndex >= restoreIndex) return;
      visibleVersions.slice(0, restoreIndex).forEach((item, index) => {
        if (item.source !== "luna") return;
        if (index > targetIndex) cancelled.add(item.id);
        else cancelled.delete(item.id);
      });
    });
    return visibleVersions
      .filter(version => version.source === "luna" && version.instruction)
      .flatMap(version => [
        { id: `${version.id}-user`, role: "user" as const, text: version.instruction, versionId: version.id,
          screenshot: version.screenshot_data_url, images: version.images || [], cancelled: cancelled.has(version.id) },
        { id: version.id, role: "luna" as const, text: version.message, versionId: version.id,
          screenshot: null, images: [] as string[], cancelled: cancelled.has(version.id) },
      ]);
  }, [visibleVersions]);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);


  // L'apercu masque ce qui deborde : la bulle doit rester dedans, quitte a
  // passer au-dessus du cadre quand il n'y a plus la place en dessous.
  useLayoutEffect(() => {
    const bubble = bubbleBoxRef.current;
    const canvas = canvasRef.current;
    if (!selection || !bubble || !canvas) return;
    const { width, height } = bubble.getBoundingClientRect();
    const { rect } = selection;
    const below = rect.y + rect.height + 10;
    const above = rect.y - height - 10;
    const fits = below + height <= canvas.clientHeight;
    setBubblePosition({
      left: Math.max(0, Math.min(rect.x, canvas.clientWidth - width)),
      top: Math.max(0, fits ? below : above >= 0 ? above : canvas.clientHeight - height),
    });
  }, [selection, zoneAttachments.length]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const pointer = dragPointer.current;
      if (pointer?.element.hasPointerCapture(pointer.id)) pointer.element.releasePointerCapture(pointer.id);
      dragPointer.current = null;
      dragStart.current = null;
      dragRectRef.current = null;
      setSelection(null);
      setZoneInstruction("");
      setZoneAttachments([]);
      setDragRect(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function pointIn(event: React.PointerEvent) {
    const bounds = canvasRef.current!.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  }

  function startDrag(event: React.PointerEvent) {
    if (event.button !== 0 || (event.target as HTMLElement).isContentEditable) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragPointer.current = { element: event.currentTarget, id: event.pointerId };
    dragStart.current = pointIn(event);
    dragRectRef.current = null;
    setSelection(null);
    setZoneInstruction("");
    setZoneAttachments([]);
    setDragRect(null);
  }

  function moveDrag(event: React.PointerEvent) {
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

  async function endDrag(event: React.PointerEvent) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    dragPointer.current = null;
    const rect = dragRectRef.current;
    dragStart.current = null;
    dragRectRef.current = null;
    setDragRect(null);
    if (!rect || rect.width < 12 || rect.height < 12) return; // un simple clic n'est pas une selection

    const frame = pageFrameRef.current;
    const page = frame?.contentDocument?.documentElement;
    if (!frame || !page) return;
    const kept = elementsInside(canvasRef.current!, rect, frame);
    setBubblePosition(null);
    const label = kept.length ? kept.slice(0, 3).join(", ") : "Page complète";
    const frameBounds = frame.getBoundingClientRect();
    const canvasBounds = canvasRef.current!.getBoundingClientRect();
    const pageBounds = page.getBoundingClientRect();
    const rawRect = {
      x: rect.x + canvasBounds.left - frameBounds.left - pageBounds.left,
      y: rect.y + canvasBounds.top - frameBounds.top - pageBounds.top,
      width: rect.width, height: rect.height,
    };
    const pageWidth = Math.max(1, page.scrollWidth);
    const pageHeight = Math.max(1, page.scrollHeight);
    const captureRect = {
      x: Math.max(0, rawRect.x),
      y: Math.max(0, rawRect.y),
      width: Math.max(0, Math.min(pageWidth, rawRect.x + rawRect.width) - Math.max(0, rawRect.x)),
      height: Math.max(0, Math.min(pageHeight, rawRect.y + rawRect.height) - Math.max(0, rawRect.y)),
    };
    if (!captureRect.width || !captureRect.height) return;
    const percentRect = {
      x: 100 * captureRect.x / pageWidth,
      y: 100 * captureRect.y / pageHeight,
      width: 100 * captureRect.width / pageWidth,
      height: 100 * captureRect.height / pageHeight,
    };
    const key = ++selectionKey.current;
    setSelection({ key, rect, percentRect, ids: kept, label, capturing: true });
    setTimeout(() => bubbleRef.current?.focus(), 30);
    try {
      const dataUrl = await captureRegion(page, captureRect);
      setSelection(current => current?.key === key ? { ...current, dataUrl, capturing: false } : current);
    } catch {
      // Sans capture, la demande part quand meme avec les elements encadres.
      setSelection(current => current?.key === key ? { ...current, capturing: false } : current);
    }
  }

  async function send(event: FormEvent, zoneText?: string) {
    event.preventDefault();
    const text = (zoneText ?? instruction).trim();
    if (!text || busy || selection?.capturing) return;
    const isZoneRequest = zoneText !== undefined;
    const current = selection;
    const joined = isZoneRequest ? zoneAttachments : attachments;
    setBusy(true);
    setError("");
    setProgressiveHtml(null);
    lastPreviewAt.current = 0;
    // Tout ce qui part quitte la zone de saisie immediatement.
    setPending({ text, screenshot: current?.dataUrl || null, images: joined });
    setInstruction("");
    setZoneInstruction("");
    if (isZoneRequest) setZoneAttachments([]);
    else setAttachments([]);
    setSelection(null);
    try {
      const result = await streamRefinement(form.id, {
        instruction: text,
        element_ids: current?.ids || [],
        region: current?.ids.length === 1 && /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(current.ids[0]) ? current.ids[0] : null,
        selection_rect: current?.percentRect || null,
        selection_label: (current?.label || (targetPage ? "Page complète" : "Formulaire complet")).slice(0, 200),
        view,
        page_id: targetPage?.id || null,
        screenshot_data_url: current?.dataUrl || null,
        images: joined,
      }, event => {
        if (event.type === "reset") {
          setProgressiveHtml(null);
          lastPreviewAt.current = 0;
        } else if (event.type === "preview" && !event.region) {
          const now = Date.now();
          if (now - lastPreviewAt.current >= 250) {
            lastPreviewAt.current = now;
            setProgressiveHtml(previewDocument(event.html));
          }
        }
      });
      onFormChange(result.form);
      if (targetPage) await onTargetPageChange?.(targetPage.id);
      setProgressiveHtml(null);
      setVersions(existing => existing.some(version => version.id === result.version.id)
        ? existing : [...existing, result.version]);
      loadVersions();
    } catch (err) {
      setProgressiveHtml(null);
      setError(err instanceof Error ? err.message : "Luna n’a pas pu appliquer la modification.");
      setSelection(current);
      if (isZoneRequest) {
        setZoneInstruction(text);
        setZoneAttachments(joined);
      } else {
        setInstruction(text);
        setAttachments(joined);
      }
    } finally {
      setPending(null);
      setBusy(false);
    }
  }

  async function act(path: string) {
    setBusy(true);
    setError("");
    try {
      const updated = await api<Form>(`/forms/${form.id}${path}`, { method: "POST" });
      onFormChange(updated);
      if (targetPage) await onTargetPageChange?.(targetPage.id);
      loadVersions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action impossible");
    } finally {
      setBusy(false);
    }
  }

  /** Annuler une etape, c'est revenir a la version qui la precede. */
  function undoTo(versionId: string) {
    const index = visibleVersions.findIndex(version => version.id === versionId);
    const previous = visibleVersions[index - 1];
    if (previous) void act(`/versions/${previous.id}/restore`);
  }

  async function attachFiles(files: File[], target: "chat" | "zone" = "chat") {
    if (!files.length) return;
    try {
      const added = await Promise.all(files.slice(0, 3).map(file => readImageAsDataUrl(file, 1400)));
      const addTo = target === "zone" ? setZoneAttachments : setAttachments;
      addTo(current => [...current, ...added].slice(0, 3));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image illisible");
    }
  }

  /** Coller une capture d'ecran dans le chat ou dans la bulle. */
  function onPaste(event: React.ClipboardEvent) {
    const files = Array.from(event.clipboardData.files).filter(file => file.type.startsWith("image/"));
    if (!files.length) return;
    event.preventDefault();
    const target = (event.target as Element).closest(".selection-bubble") ? "zone" : "chat";
    void attachFiles(files, target);
  }

  function cancelDrag(event: React.PointerEvent) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    dragPointer.current = null;
    dragStart.current = null;
    dragRectRef.current = null;
    setDragRect(null);
  }

  return <div className="luna-editor" onPaste={onPaste}>
    <div className="editor-bar">
      <span className={`draft-state ${hasDraft ? "pending" : ""}`}>{hasDraft ? "Brouillon non publié" : targetPage ? "À jour avec la page en ligne" : "À jour avec le formulaire en ligne"}</span>
      {targetPage ? <strong>{targetPage.role === "landing" ? "Page d’accueil" : targetPage.role === "form" ? "Formulaire" : "Page du tunnel"}</strong> : <div className="segment-control">
        <button className={view === "form" ? "selected" : ""} onClick={() => setView("form")}>Formulaire</button>
        <button className={view === "thanks" ? "selected" : ""} onClick={() => setView("thanks")}>Remerciement</button>
      </div>}
      <div className="segment-control">
        <button className={device === "desktop" ? "selected" : ""} onClick={() => setDevice("desktop")} aria-label="Aperçu ordinateur"><Monitor size={16}/></button>
        <button className={device === "mobile" ? "selected" : ""} onClick={() => setDevice("mobile")} aria-label="Aperçu mobile"><Smartphone size={16}/></button>
      </div>
      <span className="editor-bar-spacer"/>
      {hasDraft && <button className="button button-secondary" onClick={() => void act("/draft/discard")} disabled={busy}><X size={16}/>Abandonner</button>}
      <button className="button button-primary" onClick={() => void act("/draft/publish")} disabled={!hasDraft || busy}><Check size={16}/>Publier les modifications</button>
    </div>
    {form.field_warnings && form.field_warnings.length > 0 && <div className="editor-field-warnings" role="alert">
      <strong>Champs liés à des réponses existantes</strong>
      <ul>{form.field_warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul>
      <p>Les anciennes réponses restent consultables dans l’historique et les exports.</p>
    </div>}

    <div className="editor-columns">
      <section className="editor-preview-panel">
        <p className="editor-hint"><MousePointer2 size={15}/>Encadrez une zone à la souris pour demander une modification.</p>
        <div className={`editor-canvas device-${device}`}>
          <div
            ref={canvasRef}
            className="editor-selection-layer"
            onPointerDown={startDrag}
            onPointerMove={moveDrag}
            onPointerUp={event => void endDrag(event)}
            onPointerCancel={cancelDrag}
          >
            <div className="editor-form-frame">
              <PageFrame html={pageHtml} title={`Aperçu de ${draft.name}`} mode="edit" onReady={frame => { pageFrameRef.current = frame; }}/>
            </div>
            <div className="editor-pointer-layer" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={event => void endDrag(event)} onPointerCancel={cancelDrag}/>
            {dragRect && <div className="selection-rect" style={{ left: dragRect.x, top: dragRect.y, width: dragRect.width, height: dragRect.height }}/>}
            {selection && <>
              <div className="selection-rect kept" style={{ left: selection.rect.x, top: selection.rect.y, width: selection.rect.width, height: selection.rect.height }}/>
              <form ref={bubbleBoxRef} className="selection-bubble" style={bubblePosition || { left: selection.rect.x, top: selection.rect.y + selection.rect.height + 10, visibility: "hidden" }} onSubmit={event => void send(event, zoneInstruction)} onPointerDown={event => event.stopPropagation()}>
                <span title={selection.label}>{selection.label}</span>
                <div className="bubble-capture">
                  {selection.capturing
                    ? <><LoaderCircle className="spin" size={14}/>Capture de la zone…</>
                    : selection.dataUrl
                      ? <><img src={selection.dataUrl} alt="Capture de la zone encadrée"/>Capture jointe</>
                      : <><X size={14}/>Capture indisponible, la zone reste transmise</>}
                </div>
                <textarea ref={bubbleRef} value={zoneInstruction} maxLength={800} placeholder="Que voulez-vous changer ici ?" onChange={event => setZoneInstruction(event.target.value)} disabled={!configured || busy}/>
                {zoneAttachments.length > 0 && <Attachments images={zoneAttachments} onRemove={index => setZoneAttachments(current => current.filter((_, position) => position !== index))} onAdd={() => undefined} allowAdd={false}/>}
                <div>
                  <button type="button" onClick={() => { setSelection(null); setZoneInstruction(""); setZoneAttachments([]); }}>Annuler</button>
                  <button className="button button-primary" disabled={!zoneInstruction.trim() || !configured || busy || selection.capturing}>{busy || selection.capturing ? <LoaderCircle className="spin" size={15}/> : <Send size={15}/>}Envoyer</button>
                </div>
              </form>
            </>}
          </div>
        </div>
      </section>

      <aside className="luna-chat-panel">
        <header className="luna-chat-head">
          <div className="luna-chat-avatar"><Sparkles size={18}/></div>
          <div><strong>Luna</strong><span>{configured ? "Connectée · recherche web disponible" : "Indisponible"}</span></div>
          <i className={configured ? "online" : ""}/>
        </header>
        <div className="luna-chat-messages" ref={messagesRef}>
          {!messages.length && <div className="chat-message assistant"><p>{configured ? "Encadrez une zone, ou demandez à Luna de consulter un site public pour s’appuyer sur ses informations." : "Luna est indisponible tant que la clé OpenAI n’est pas configurée sur le serveur."}</p></div>}
          {messages.map(message => <div className={`chat-message ${message.role === "luna" ? "assistant" : "user"}${message.cancelled ? " cancelled" : ""}`} key={message.id}>
            {message.role === "user" && <MessageImages screenshot={message.screenshot} images={message.images}/>}
            <p>{message.text}</p>
            {message.role === "luna" && (message.cancelled
              ? <span className="chat-cancelled"><Undo2 size={13}/>Modification annulée</span>
              : <button className="chat-undo" onClick={() => undoTo(message.versionId)} disabled={busy}><Undo2 size={13}/>Annuler cette modification</button>)}
          </div>)}
          {pending && <div className="chat-message user">
            <MessageImages screenshot={pending.screenshot} images={pending.images}/>
            <p>{pending.text}</p>
          </div>}
          {busy && <div className="chat-message assistant thinking"><span/><span/><span/></div>}
          {error && <div className="chat-message assistant error"><p>{error}</p></div>}
        </div>
        <form className="luna-chat-composer" onSubmit={event => void send(event)}>
          <textarea value={instruction} maxLength={800} placeholder="Ex. Rends le bouton plus visible…" onChange={event => setInstruction(event.target.value)} disabled={!configured || busy}/>
          <Attachments images={attachments} onRemove={index => setAttachments(current => current.filter((_, position) => position !== index))} onAdd={attachFiles}/>
          <div className="composer-actions">
            <span className="composer-target">{selection ? selection.label : targetPage ? "Page complète" : "Formulaire complet"}</span>
            <button className="chat-send" disabled={!instruction.trim() || !configured || busy || selection?.capturing} aria-label="Envoyer à Luna"><Send size={17}/></button>
          </div>
          {!configured && <p className="composer-help">Luna n’est pas connectée. Un administrateur doit renseigner la clé du service d’IA.</p>}
        </form>
      </aside>
    </div>
  </div>;
}

type RefinementResult = { message: string; form: Form; version: Version };
type RefinementEvent =
  | { type: "preview"; html: string; region: string | null }
  | { type: "reset" }
  | ({ type: "final" } & RefinementResult)
  | { type: "error"; message: string };

/** L'API répond en SSE sur une requête POST authentifiée. */
async function streamRefinement(formId: string, body: object, onEvent: (event: RefinementEvent) => void): Promise<RefinementResult> {
  const headers = new Headers({ "Content-Type": "application/json", Accept: "text/event-stream" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}/forms/${formId}/luna/refine/stream`, {
    method: "POST", headers, body: JSON.stringify(body), cache: "no-store",
  });
  if (response.status === 401) {
    localStorage.removeItem("sillage_token");
    window.location.replace("/");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(" · ")
      : data.detail;
    throw new Error(detail || "Luna n’a pas pu démarrer la modification.");
  }
  if (!response.body) throw new Error("Le flux de Luna est indisponible.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: RefinementResult | null = null;
  const consume = (block: string) => {
    const payload = block.split("\n").filter(line => line.startsWith("data:"))
      .map(line => line.slice(5).trimStart()).join("\n");
    if (!payload) return;
    const event = JSON.parse(payload) as RefinementEvent;
    if (event.type === "error") throw new Error(event.message || "Luna n’a pas pu appliquer la modification.");
    if (event.type === "final") result = event;
    onEvent(event);
  };
  try {
    while (!result) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        consume(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (result) break;
        boundary = buffer.indexOf("\n\n");
      }
    }
    if (!result) throw new Error("La réponse de Luna s’est interrompue.");
    return result;
  } finally {
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

/** Le document partiel ne peut charger ni script, ni ressource distante. */
function previewDocument(html: string): string {
  const csp = "default-src 'none'; base-uri 'none'; form-action 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:";
  const meta = `<meta http-equiv="Content-Security-Policy" content="${csp}">`;
  if (/<head\b[^>]*>/i.test(html)) return html.replace(/<head\b[^>]*>/i, match => `${match}${meta}`);
  const doctype = html.match(/^\s*<!doctype[^>]*>/i);
  if (doctype) return `${doctype[0]}${meta}${html.slice(doctype[0].length)}`;
  return `${meta}${html}`;
}

function MessageImages({ screenshot, images }: { screenshot?: string | null; images: string[] }) {
  if (!screenshot && !images.length) return null;
  return <div className="chat-message-images">
    {screenshot && <img src={screenshot} alt="Capture de la zone sélectionnée" title="Capture de la zone"/>}
    {images.map((image, index) => <img key={index} src={image} alt={`Pièce jointe ${index + 1}`} title="Pièce jointe"/>)}
  </div>;
}

/** Images jointes a la demande : capture externe, inspiration, photo. */
function Attachments({ images, onRemove, onAdd, allowAdd = true }: {
  images: string[]; onRemove: (index: number) => void; onAdd: (files: File[]) => void; allowAdd?: boolean;
}) {
  return <div className="chat-attachments">
    {images.map((image, index) => <span key={`${index}-${image.slice(-24)}`}>
      <img src={image} alt={`Image jointe ${index + 1}`}/>
      <button type="button" onClick={() => onRemove(index)} aria-label="Retirer l’image"><X size={11}/></button>
    </span>)}
    {allowAdd && images.length < 3 && <label className="chat-attach" title="Joindre une image (ou collez une capture)">
      <ImagePlus size={15}/>
      <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={event => {
        const files = Array.from(event.target.files || []);
        event.target.value = "";
        onAdd(files);
      }}/>
    </label>}
  </div>;
}
