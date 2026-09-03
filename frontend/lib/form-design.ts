import type { FormDesign } from "@/lib/types";

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
  return `design-background-${normalizeDesign(design).background}`;
}
