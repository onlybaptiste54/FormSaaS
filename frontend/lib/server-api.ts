/**
 * Adresses vues depuis le serveur Next, pas depuis le navigateur.
 *
 * Dans un conteneur, localhost désigne le front lui-même et non l'API : le
 * rendu serveur doit donc passer par l'adresse interne.
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
 * l'adresse externe sans la suivre. Les visuels de marque passent par le même
 * chemin : ils doivent être servis à la même origine que la page.
 *
 * L'adresse du visiteur part avec la requête. Sans elle, l'API verrait celle du
 * serveur web pour tout le monde, et un seul compteur de débit bloquerait tous
 * les visiteurs à la fois. L'API ne la croit que si elle vient de ce serveur.
 */
export async function relayPublicPage(path: string, request: Request): Promise<Response> {
  let upstream: Response;
  try {
    const headers: Record<string, string> = { cookie: request.headers.get("cookie") || "" };
    // Next la remplit avec l'adresse de la connexion si aucun proxy ne l'a posée.
    const visitor = request.headers.get("x-forwarded-for");
    if (visitor) headers["x-forwarded-for"] = visitor;
    upstream = await fetch(`${SERVER_API_URL}${path}`, { headers, redirect: "manual", cache: "no-store" });
  } catch {
    return new Response("Cette page est momentanément indisponible.", {
      status: 502, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }
  // Sans consigne de l'API, rien n'est mis en cache : le parcours dépend du cookie.
  const headers = new Headers({ "cache-control": upstream.headers.get("cache-control") || "no-store" });
  for (const name of ["content-type", "location", "x-content-type-options", "content-security-policy"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  for (const cookie of upstream.headers.getSetCookie()) headers.append("set-cookie", cookie);
  const redirected = upstream.status >= 300 && upstream.status < 400;
  // Octets bruts : le même relais transmet des pages et des images.
  return new Response(redirected ? null : await upstream.arrayBuffer(), { status: upstream.status, headers });
}
