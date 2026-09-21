"use client";

import { FormEvent, MouseEvent, useEffect, useRef, useState } from "react";
import { Camera, Check, Image as ImageIcon, LoaderCircle, MousePointer2, Send, Sparkles, X } from "lucide-react";
import { toPng } from "html-to-image";
import { FormRenderer, FormStage } from "@/components/form-renderer";
import { api } from "@/lib/api";
import type { Campaign, Me } from "@/lib/types";

type Selection = {
  kind: "form" | "header" | "field" | "button";
  id?: string;
  label: string;
};

type Capture = Selection & { dataUrl?: string };
type ChatMessage = { id: string; role: "assistant" | "user"; text: string; capture?: Capture; error?: boolean };
type LunaStatus = { configured: boolean; provider: string; model: string | null };

const WELCOME_MESSAGES: ChatMessage[] = [
  { id: "welcome", role: "assistant", text: "Sélectionnez une zone ou décrivez directement ce que vous souhaitez modifier." },
];

/** Nombre de messages conserves par campagne dans le stockage local. */
const CHAT_HISTORY_LIMIT = 40;

export function LunaFormEditor({ campaign, onCampaignChange }: { campaign: Campaign; onCampaignChange: (campaign: Campaign) => void }) {
  const [company, setCompany] = useState<Me["company"] | null>(null);
  const [status, setStatus] = useState<LunaStatus | null>(null);
  const [captureMode, setCaptureMode] = useState(false);
  const [captureBusy, setCaptureBusy] = useState(false);
  const [pendingCapture, setPendingCapture] = useState<Capture | null>(null);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(WELCOME_MESSAGES);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const storageKey = `luna-chat-${campaign.id}`;

  useEffect(() => {
    void api<Me>("/me").then(data => setCompany(data.company));
    void api<LunaStatus>("/luna/status").then(setStatus);
  }, []);

  // Restauration au montage : la lecture se fait dans un effet, pas dans le
  // useState, pour ne pas desynchroniser le rendu serveur de Next.
  useEffect(() => {
    let saved: ChatMessage[] | null = null;
    try {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : null;
      if (Array.isArray(parsed) && parsed.length) saved = parsed as ChatMessage[];
    } catch {
      saved = null;
    }
    setMessages(saved || WELCOME_MESSAGES);
  }, [storageKey]);

  // Les captures PNG ne sont pas persistees : elles satureraient le quota.
  // Le libelle de la zone reste affiche.
  useEffect(() => {
    if (messages.length <= 1) return;
    try {
      const persisted = messages.slice(-CHAT_HISTORY_LIMIT).map(message =>
        message.capture ? { ...message, capture: { ...message.capture, dataUrl: undefined } } : message,
      );
      localStorage.setItem(storageKey, JSON.stringify(persisted));
    } catch {
      // Quota depasse ou stockage indisponible : la conversation reste en memoire.
    }
  }, [messages, storageKey]);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const clientColors = {
    "--client": company?.primary_color || "#2F6B4F",
    "--client-accent": company?.accent_color || "#EE755C",
  } as React.CSSProperties;

  async function captureTarget(event: MouseEvent<HTMLElement>) {
    if (!captureMode) return;
    const element = (event.target as HTMLElement).closest<HTMLElement>("[data-luna-id]");
    if (!element) return;
    event.preventDefault();
    event.stopPropagation();
    const selection = selectionFor(element.dataset.lunaId || "card");
    setCaptureBusy(true);
    setCaptureMode(false);
    try {
      let dataUrl = await toPng(element, { cacheBust: true, pixelRatio: 2 });
      if (dataUrl.length > 3_800_000) {
        dataUrl = await toPng(element, { cacheBust: true, pixelRatio: 1 });
      }
      if (dataUrl.length > 3_800_000) throw new Error("Capture trop volumineuse");
      setPendingCapture({ ...selection, dataUrl });
      textareaRef.current?.focus();
    } catch {
      setMessages(current => [...current, { id: crypto.randomUUID(), role: "assistant", text: "La capture a échoué. Vous pouvez réessayer sur une zone plus petite.", error: true }]);
    } finally {
      setCaptureBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = instruction.trim();
    if (!text || busy) return;
    const selection: Selection = pendingCapture || { kind: "form", label: "Formulaire complet" };
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", text, capture: pendingCapture || undefined };
    setMessages(current => [...current, userMessage]);
    setBusy(true);
    try {
      const result = await api<{ message: string; campaign: Campaign }>(`/campaigns/${campaign.id}/luna/refine`, {
        method: "POST",
        body: JSON.stringify({
          instruction: text,
          selection_kind: selection.kind,
          selection_id: selection.id || null,
          selection_label: selection.label,
          screenshot_data_url: pendingCapture?.dataUrl || null,
        }),
      });
      onCampaignChange(result.campaign);
      setMessages(current => [...current, { id: crypto.randomUUID(), role: "assistant", text: result.message }]);
      setInstruction("");
      setPendingCapture(null);
    } catch (error) {
      setMessages(current => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: error instanceof Error ? error.message : "Luna n’a pas pu appliquer la modification.",
        error: true,
      }]);
    } finally {
      setBusy(false);
    }
  }

  return <div className="detail-content luna-editor">
    <section className={`editor-preview-panel ${captureMode ? "capture-mode" : ""}`}>
      <div className="editor-toolbar">
        <div>
          <p className="eyebrow">APERÇU EN DIRECT</p>
          <strong>{captureMode ? "Cliquez sur la zone à modifier" : "Votre formulaire"}</strong>
        </div>
        <button className={`button button-secondary ${captureMode ? "active" : ""}`} onClick={() => setCaptureMode(value => !value)} disabled={captureBusy}>
          {captureBusy ? <LoaderCircle className="spin" size={17}/> : captureMode ? <X size={17}/> : <Camera size={17}/>}
          {captureBusy ? "Capture…" : captureMode ? "Annuler" : "Capturer une zone"}
        </button>
      </div>
      {captureMode && <div className="capture-guide"><MousePointer2 size={16}/>Cliquez sur la zone à modifier : titre, champ, bouton ou formulaire entier.</div>}
      <FormStage design={campaign.design} className="editor-canvas" style={clientColors}>
        <div className="editor-form-frame" onClickCapture={event => void captureTarget(event)}>
          <FormRenderer form={campaign} company={{ name: company?.name || "Votre entreprise" }} mode="edit"/>
        </div>
      </FormStage>
    </section>

    <aside className="luna-chat-panel">
      <header className="luna-chat-head">
        <div className="luna-chat-avatar"><Sparkles size={18}/></div>
        <div><strong>Luna</strong><span>{status?.configured ? "Connectée" : "Indisponible"}</span></div>
        <i className={status?.configured ? "online" : ""}/>
      </header>
      <div className="luna-chat-messages" ref={messagesRef}>
        {messages.map(message => <div className={`chat-message ${message.role} ${message.error ? "error" : ""}`} key={message.id}>
          {message.capture && <div className="chat-capture">{message.capture.dataUrl && <img src={message.capture.dataUrl} alt={`Capture : ${message.capture.label}`}/>}<span><ImageIcon size={13}/>{message.capture.label}</span></div>}
          <p>{message.text}</p>
        </div>)}
        {busy && <div className="chat-message assistant thinking"><span/><span/><span/></div>}
      </div>
      <form className="luna-chat-composer" onSubmit={submit}>
        {pendingCapture && <div className="pending-capture">
          <img src={pendingCapture.dataUrl} alt={`Capture : ${pendingCapture.label}`}/>
          <span><ImageIcon size={14}/><strong>{pendingCapture.label}</strong> jointe au message</span>
          <button type="button" onClick={() => setPendingCapture(null)} aria-label="Retirer la capture"><X size={15}/></button>
        </div>}
        <textarea ref={textareaRef} value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="Ex. Centre le titre et rends les champs plus doux…" maxLength={800} disabled={!status?.configured || busy}/>
        <div className="composer-actions">
          <button type="button" className="capture-shortcut" onClick={() => setCaptureMode(true)} disabled={captureMode || captureBusy}><Camera size={16}/><span>Capturer</span></button>
          <span>{instruction.length}/800</span>
          <button className="chat-send" disabled={!instruction.trim() || !status?.configured || busy} aria-label="Envoyer à Luna"><Send size={17}/></button>
        </div>
        {status && !status.configured && <p className="composer-help">Luna n’est pas encore connectée. Un administrateur doit renseigner la clé du service d’IA.</p>}
      </form>
    </aside>
  </div>;
}

/** Traduit un data-luna-id du rendu en selection comprise par l'API. */
function selectionFor(lunaId: string): Selection {
  if (lunaId.startsWith("field:")) {
    const [, rest] = lunaId.split(":");
    const id = rest.replace(".label", "");
    return { kind: "field", id, label: `Champ « ${id} »` };
  }
  if (lunaId === "submit") return { kind: "button", label: "Bouton d’envoi" };
  if (["eyebrow", "title", "description", "brand"].includes(lunaId)) return { kind: "header", label: "En-tête du formulaire" };
  return { kind: "form", label: "Formulaire complet" };
}
