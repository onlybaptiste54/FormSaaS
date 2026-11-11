/**
 * Adresses vues depuis le serveur Next, pas depuis le navigateur.
 *
 * Dans un conteneur, localhost désigne le front lui-même et non l'API : le
 * rendu serveur doit donc passer par l'adresse interne, celle que la
 * réécriture des visuels de marque utilise déjà.
 */
export const SERVER_API_URL = process.env.API_INTERNAL_URL
  ? `${process.env.API_INTERNAL_URL}/api`
  : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

/** Adresse publique du site, pour les liens absolus du sitemap et des aperçus. */
export const SITE_URL = (process.env.SITE_URL || "http://localhost:3000").replace(/\/$/, "");

/**
 * Relaie une réponse de l'API telle quelle vers le visiteur.
 *
 * La page publique d'un tunnel de vente est le document généré lui-même, servi
 * seul. Le serveur Next ne fait que le transmettre : il passe le cookie de
 * parcours dans les deux sens, et laisse la redirection finale repartir vers
 * l'adresse externe sans la suivre.
 */
export async function relayPublicPage(path: string, request: Request): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${SERVER_API_URL}${path}`, {
      headers: { cookie: request.headers.get("cookie") || "" },
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return new Response("Cette page est momentanément indisponible.", {
      status: 502, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }
  const headers = new Headers({ "cache-control": "no-store" });
  const type = upstream.headers.get("content-type");
  if (type) headers.set("content-type", type);
  const location = upstream.headers.get("location");
  if (location) headers.set("location", location);
  for (const cookie of upstream.headers.getSetCookie()) headers.append("set-cookie", cookie);
  const redirected = upstream.status >= 300 && upstream.status < 400;
  return new Response(redirected ? null : await upstream.text(), { status: upstream.status, headers });
}
