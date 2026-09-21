import type { CSSProperties } from "react";
import type { FormDesign, FormStyle } from "@/lib/types";

const FONT_STACKS: Record<FormStyle["font"], string> = {
  sans: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  grotesk: "'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif",
  serif: "Georgia, 'Times New Roman', serif",
  mono: "ui-monospace, 'Cascadia Mono', Menlo, monospace",
};

/** "#0B0F1A" -> "11 15 26", pour composer rgb(... / alpha) en CSS. */
function rgbChannels(hex: string) {
  const value = hex.replace("#", "");
  return [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16)).join(" ");
}

/** Fonds des anciennes campagnes, avant que Luna ne choisisse ses couleurs. */
const LEGACY_BACKGROUNDS: Record<string, { from: string; to: string; dark: boolean }> = {
  warm: { from: "#efeee8", to: "#efeee8", dark: false },
  mist: { from: "#eaf0ed", to: "#eaf0ed", dark: false },
  white: { from: "#ffffff", to: "#ffffff", dark: false },
  ink: { from: "#17231d", to: "#17231d", dark: true },
};

const LEGACY_RADIUS: Record<string, number> = { subtle: 7, rounded: 18, pill: 28 };

export const DEFAULT_FORM_STYLE: FormStyle = {
  page_from: "#efeee8",
  page_to: "#efeee8",
  surface: "#ffffff",
  surface_alpha: 1,
  border: "#d9ddd6",
  border_alpha: 1,
  ink: "#17211b",
  ink_soft: "#566159",
  accent: "#2f6b4f",
  accent_ink: "#ffffff",
  blur_px: 0,
  radius_px: 18,
  glow: 0,
  font: "sans",
  heading_font: "serif",
  title_scale: 1,
  title_case: "normal",
};

export const DEFAULT_FORM_DESIGN: FormDesign = {
  layout: "card",
  density: "comfortable",
  field_style: "outline",
  button_style: "solid",
  heading_align: "left",
  style: DEFAULT_FORM_STYLE,
};

/**
 * Style deduit des anciens tokens (background, radius) pour les campagnes
 * creees avant le style libre : un seul chemin de rendu ensuite.
 */
export function styleFromLegacy(design?: Partial<FormDesign>): FormStyle {
  const background = LEGACY_BACKGROUNDS[design?.background || "warm"] || LEGACY_BACKGROUNDS.warm;
  return {
    ...DEFAULT_FORM_STYLE,
    page_from: background.from,
    page_to: background.to,
    surface: background.dark ? "#1e2b24" : "#ffffff",
    border: background.dark ? "#3a4a41" : "#d9ddd6",
    ink: background.dark ? "#f2f5f1" : DEFAULT_FORM_STYLE.ink,
    ink_soft: background.dark ? "#adbab2" : DEFAULT_FORM_STYLE.ink_soft,
    radius_px: LEGACY_RADIUS[design?.radius || "rounded"] ?? LEGACY_RADIUS.rounded,
  };
}

export function normalizeDesign(design?: Partial<FormDesign>): FormDesign {
  return { ...DEFAULT_FORM_DESIGN, ...design, style: design?.style || styleFromLegacy(design) };
}

export function designClassNames(design?: Partial<FormDesign>) {
  const value = normalizeDesign(design);
  return [
    "form-design",
    `design-layout-${value.layout}`,
    `design-density-${value.density}`,
    `design-fields-${value.field_style}`,
    `design-button-${value.button_style}`,
    `design-heading-${value.heading_align}`,
  ].join(" ");
}

/** La page applique toujours le style : couleurs, fond et police viennent de lui. */
export function backgroundClassName(_design?: Partial<FormDesign>) {
  return "has-luna-style";
}

/**
 * Variables CSS issues du style de Luna. Rien n'est interprete comme du CSS :
 * chaque valeur vient d'un hex ou d'un nombre deja borne par le backend.
 */
export function formStyleVars(design?: Partial<FormDesign>): CSSProperties {
  const style = normalizeDesign(design).style as FormStyle;
  return {
    "--f-page-from": style.page_from,
    "--f-page-to": style.page_to,
    "--f-surface": rgbChannels(style.surface),
    "--f-surface-alpha": style.surface_alpha,
    "--f-border": rgbChannels(style.border),
    "--f-border-alpha": style.border_alpha,
    "--f-ink": style.ink,
    "--f-ink-soft": style.ink_soft,
    "--f-accent": style.accent,
    "--f-accent-rgb": rgbChannels(style.accent),
    "--f-accent-ink": style.accent_ink,
    "--f-blur": `${style.blur_px}px`,
    "--f-radius": `${style.radius_px}px`,
    "--f-glow": style.glow,
    "--f-font": FONT_STACKS[style.font] || FONT_STACKS.sans,
    "--f-heading-font": FONT_STACKS[style.heading_font || "serif"] || FONT_STACKS.serif,
    "--f-title-scale": style.title_scale ?? 1,
    "--f-title-case": style.title_case === "uppercase" ? "uppercase" : "none",
  } as CSSProperties;
}
