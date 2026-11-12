import type { NextConfig } from "next";

const apiOrigin = new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").origin;
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

// Le tunnel de vente est servi comme document entier, sans coquille d'app :
// il n'execute aucun script, et sa politique le dit aussi dans l'en-tete.
const documentCsp = [
  "default-src 'none'",
  "script-src 'none'",
  "style-src 'unsafe-inline'",
  "img-src 'self' https: data:",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
  "connect-src 'none'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Les visuels du client sont relayes par app/media/brand/route.ts.
  async headers() {
    return [
      { source: "/forms/:slug", headers: [{ key: "Content-Security-Policy", value: publicPageCsp }] },
      { source: "/t/:path*", headers: [{ key: "Content-Security-Policy", value: documentCsp }] },
    ];
  },
};

export default nextConfig;
