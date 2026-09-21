export type Field = { id: string; label: string; type: string; required?: boolean; options?: string[]; scale?: number; placeholder?: string };
export type FormStyle = {
  page_from: string;
  page_to: string;
  surface: string;
  surface_alpha: number;
  border: string;
  border_alpha: number;
  ink: string;
  ink_soft: string;
  accent: string;
  accent_ink: string;
  blur_px: number;
  radius_px: number;
  glow: number;
  font: "sans" | "grotesk" | "serif" | "mono";
  heading_font?: "sans" | "grotesk" | "serif" | "mono";
  title_scale?: number;
  title_case?: "normal" | "uppercase";
};
export type FormContent = { eyebrow: string; submit_label: string; trust_note: string };
export type FormDesign = {
  layout: "card" | "split" | "minimal";
  density: "compact" | "comfortable" | "airy";
  field_style: "outline" | "filled" | "underline";
  button_style: "solid" | "outline" | "soft";
  heading_align: "left" | "center";
  style?: FormStyle;
  brand_display?: "logo_and_name" | "logo" | "name" | "hidden";
  brand_size?: "small" | "medium" | "large";
  /** Anciens tokens, encore presents en base : convertis en style au rendu. */
  background?: "warm" | "mist" | "white" | "ink";
  radius?: "subtle" | "rounded" | "pill";
};
export type FormHealth = { score: number; checks: { label: string; ok: boolean; hint: string }[] };
export type FormDraft = Partial<Pick<Form, "name" | "description" | "fields" | "design" | "content" | "thank_you">>;
/** Le formulaire : l'objet qu'on edite avec Luna et que voit un visiteur. */
export type Form = { id: string; campaign_id: string; campaign_name: string; name: string; slug: string; description: string; kind: string; status: string; visibility: string; fields: Field[]; design: FormDesign; content: FormContent; thank_you: Record<string, string>; draft: FormDraft | null; health: FormHealth; visits: number; responses: number; conversion: number; archived: boolean; created_at: string; updated_at: string };
/** La campagne : un dossier (un client, un evenement) qui regroupe des formulaires. */
export type Campaign = { id: string; name: string; client: string; objective: string; starts_on: string | null; ends_on: string | null; forms: number; active: number; visits: number; responses: number; conversion: number; last_activity: string; archived: boolean; created_at: string; updated_at: string };
export type CampaignStats = {
  forms: number;
  active: number;
  visits: number;
  responses: number;
  conversion: number;
  best: FormBreakdown | null;
  breakdown: FormBreakdown[];
  daily: { date: string; count: number }[];
  sources: { name: string; count: number }[];
};
export type FormBreakdown = { id: string; name: string; status: string; visits: number; responses: number; conversion: number };
export type ResponseRow = { id: string; form_id: string; form: string; campaign_id: string; campaign: string; answers: Record<string, string | number>; source: string; promo_code: string; consent: boolean; consent_text: string; ip_address: string; user_agent: string; created_at: string };
export type ResponsePage = { items: ResponseRow[]; total: number; limit: number; offset: number; sources: string[] };
export type LibraryTemplate = {
  id?: string;
  key: string;
  name: string;
  category: string;
  description: string;
  fields: Field[];
  field_count: number;
  design: FormDesign;
  content: FormContent;
  thank_you: Record<string, string>;
  minutes?: number;
  accent?: string;
  uses?: number;
  created_at?: string;
  updated_at?: string;
};
export type LibraryData = { featured: LibraryTemplate[]; saved: LibraryTemplate[]; recent: Form[] };
export type Stats = { campaigns: number; forms: number; active: number; drafts: number; responses: number; week_responses: number; conversion: number; daily: { date: string; count: number }[]; sources: { name: string; count: number }[]; recent: { id: string; form_id: string; form: string; campaign: string; name: string; source: string; created_at: string }[] };
export type BrandProfile = {
  palette?: string[];
  font?: FormStyle["font"];
  tone?: string;
  rules_do?: string[];
  rules_avoid?: string[];
  summary?: string;
};
export type Company = {
  id: string;
  name: string;
  legal_name: string;
  sector: string;
  siret: string;
  address: string;
  primary_color: string;
  accent_color: string;
  tone: string;
  dpo_email: string;
  logo: string;
  brand: BrandProfile;
};
export type Me = { id: string; email: string; full_name: string; role: string; company: Company };
