import type { NextConfig } from "next";

const apiOrigin = new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").origin;
// Le relais est resolu par le serveur Next, pas par le navigateur : depuis le
// conteneur, localhost designe le front lui-meme et non l'API.
const apiInternalOrigin = process.env.API_INTERNAL_URL || apiOrigin;
const publicPageCsp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "frame-src 'self' data:",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data: https:",
  `connect-src 'self' ${apiOrigin}${process.env.NODE_ENV === "development" ? " ws://localhost:3000" : ""}`,
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Les visuels du client sont relayes par l'API, mais servis a la meme origine
  // que la page : une image d'une autre origine souille le canvas de la capture.
  async rewrites() {
    return [{ source: "/media/brand", destination: `${apiInternalOrigin}/api/brand/image` }];
  },
  async headers() {
    return ["/forms/:slug", "/t/:slug"].map(source => ({ source, headers: [{ key: "Content-Security-Policy", value: publicPageCsp }] }));
  },
};

export default nextConfig;
