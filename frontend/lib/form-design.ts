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

export const DEFAULT_FORM_DESIGN: FormDesign = {
  layout: "card",
  background: "warm",
  density: "comfortable",
  radius: "rounded",
  field_style: "outline",
  button_style: "solid",
  heading_align: "left",
};

export function normalizeDesign(design?: Partial<FormDesign>): FormDesign {
  return { ...DEFAULT_FORM_DESIGN, ...design };
}

export function designClassNames(design?: Partial<FormDesign>) {
  const value = normalizeDesign(design);
  return [
    "form-design",
    `design-layout-${value.layout}`,
    `design-density-${value.density}`,
    `design-radius-${value.radius}`,
    `design-fields-${value.field_style}`,
    `design-button-${value.button_style}`,
    `design-heading-${value.heading_align}`,
  ].join(" ");
}

export function backgroundClassName(design?: Partial<FormDesign>) {
  const value = normalizeDesign(design);
  return `design-background-${value.background}${value.style ? " has-luna-style" : ""}`;
}

/**
 * Variables CSS issues du style libre de Luna. Rien n'est interprete comme du
 * CSS : chaque valeur vient d'un hex ou d'un nombre deja borne par le backend.
 * Retourne {} pour les campagnes sans style, qui gardent le rendu historique.
 */
export function formStyleVars(design?: Partial<FormDesign>): CSSProperties {
  const style = normalizeDesign(design).style;
  if (!style) return {};
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
  } as CSSProperties;
}
