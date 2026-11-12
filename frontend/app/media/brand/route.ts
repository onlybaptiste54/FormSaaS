import { relayPublicPage } from "@/lib/server-api";

/**
 * Un visuel du site d'un client, relayé par l'API et servi à la même origine
 * que la page : une image d'une autre origine souille le canvas de la capture.
 *
 * Une réécriture de next.config ne transmettait pas l'adresse du visiteur à
 * l'API, d'où ce relais.
 */
export async function GET(request: Request) {
  return relayPublicPage(`/brand/image${new URL(request.url).search}`, request);
}
