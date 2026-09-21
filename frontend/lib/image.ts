/** Taille maximale d'une image encodee envoyee a l'API (200 Ko en base64). */
const MAX_BYTES = 270_000;

/**
 * Lit une image choisie par l'utilisateur et la redimensionne dans le
 * navigateur : le serveur ne recoit qu'une data URL legere, sans stockage
 * de fichier a gerer.
 */
export async function readImageAsDataUrl(file: File, maxSize: number): Promise<string> {
  if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
    throw new Error("Formats acceptés : PNG, JPEG ou WebP. Pour un PDF, exportez les pages en images.");
  }
  const source = await readFile(file);
  const image = await loadImage(source);

  const scale = Math.min(1, maxSize / Math.max(image.width, image.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.width * scale));
  canvas.height = Math.max(1, Math.round(image.height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Image illisible");
  context.drawImage(image, 0, 0, canvas.width, canvas.height);

  // Le PNG garde la transparence d'un logo ; on bascule en JPEG si c'est trop lourd.
  let dataUrl = canvas.toDataURL("image/png");
  for (const quality of [0.9, 0.75, 0.6]) {
    if (dataUrl.length <= MAX_BYTES) break;
    dataUrl = canvas.toDataURL("image/jpeg", quality);
  }
  if (dataUrl.length > MAX_BYTES) throw new Error("Image trop lourde : choisissez un fichier plus petit.");
  return dataUrl;
}

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Lecture impossible"));
    reader.readAsDataURL(file);
  });
}

function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Image illisible"));
    image.src = source;
  });
}
