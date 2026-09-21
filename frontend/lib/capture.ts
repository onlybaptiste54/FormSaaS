import { toPng } from "html-to-image";

/** Largeur maximale envoyee a Luna : au-dela, l'image coute plus qu'elle n'apporte. */
const MAX_WIDTH = 1200;
const MAX_BYTES = 3_800_000;

type Rect = { x: number; y: number; width: number; height: number };

/**
 * Capture la zone encadree sur le canevas, avec son vrai fond.
 *
 * On photographie le canevas entier plutot que l'element vise : un formulaire
 * en verre ou sur fond sombre garde ainsi son arriere-plan, alors qu'une
 * capture element par element le remplacait par du blanc.
 */
export async function captureRegion(canvas: HTMLElement, rect: Rect): Promise<string> {
  const ratio = 2;
  const full = await toPng(canvas, { cacheBust: true, pixelRatio: ratio, filter: node => !(node instanceof HTMLElement) || !node.classList.contains("selection-rect") });
  const image = await loadImage(full);

  const scale = Math.min(1, MAX_WIDTH / (rect.width * ratio));
  const output = document.createElement("canvas");
  output.width = Math.max(1, Math.round(rect.width * ratio * scale));
  output.height = Math.max(1, Math.round(rect.height * ratio * scale));
  const context = output.getContext("2d");
  if (!context) throw new Error("Capture impossible");
  context.drawImage(image, rect.x * ratio, rect.y * ratio, rect.width * ratio, rect.height * ratio, 0, 0, output.width, output.height);

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
