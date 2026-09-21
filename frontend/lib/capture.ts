import { toPng } from "html-to-image";

/** Largeur maximale envoyee a Luna : au-dela, l'image coute plus qu'elle n'apporte. */
const MAX_WIDTH = 1200;
const MAX_BYTES = 3_800_000;
/** Marge autour de la zone encadree, pour que Luna voie l'environnement. */
const CONTEXT_RATIO = 0.55;
const MIN_CONTEXT = 120;

type Rect = { x: number; y: number; width: number; height: number };

/**
 * Capture la zone encadree avec son environnement.
 *
 * On photographie le canevas entier (le vrai fond est donc conserve, y compris
 * sur un formulaire sombre ou en verre), puis on recadre autour de la zone en
 * gardant une marge, et on redessine le cadre de selection sur l'image : Luna
 * voit a la fois ce qui est vise et ce qui l'entoure.
 */
export async function captureRegion(canvas: HTMLElement, rect: Rect, accent = "#2F6B4F"): Promise<string> {
  const ratio = 2;
  const full = await toPng(canvas, {
    cacheBust: true,
    pixelRatio: ratio,
    filter: node => !(node instanceof HTMLElement) || !node.classList.contains("selection-rect"),
  });
  const image = await loadImage(full);

  const margin = Math.max(MIN_CONTEXT, Math.max(rect.width, rect.height) * CONTEXT_RATIO);
  const area = {
    x: Math.max(0, rect.x - margin),
    y: Math.max(0, rect.y - margin),
    width: 0,
    height: 0,
  };
  area.width = Math.min(image.width / ratio - area.x, rect.width + (rect.x - area.x) + margin);
  area.height = Math.min(image.height / ratio - area.y, rect.height + (rect.y - area.y) + margin);

  const scale = Math.min(1, MAX_WIDTH / (area.width * ratio));
  const output = document.createElement("canvas");
  output.width = Math.max(1, Math.round(area.width * ratio * scale));
  output.height = Math.max(1, Math.round(area.height * ratio * scale));
  const context = output.getContext("2d");
  if (!context) throw new Error("Capture impossible");

  context.drawImage(
    image,
    area.x * ratio, area.y * ratio, area.width * ratio, area.height * ratio,
    0, 0, output.width, output.height,
  );

  // Le cadre indique a Luna la zone exactement visee dans cet environnement.
  context.strokeStyle = accent;
  context.lineWidth = Math.max(2, 3 * ratio * scale);
  context.strokeRect(
    (rect.x - area.x) * ratio * scale,
    (rect.y - area.y) * ratio * scale,
    rect.width * ratio * scale,
    rect.height * ratio * scale,
  );

  let dataUrl = output.toDataURL("image/png");
  if (dataUrl.length > MAX_BYTES) dataUrl = output.toDataURL("image/jpeg", 0.85);
  if (dataUrl.length > MAX_BYTES) throw new Error("Capture trop volumineuse");
  return dataUrl;
}

function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Capture illisible"));
    image.src = source;
  });
}
