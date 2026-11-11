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
