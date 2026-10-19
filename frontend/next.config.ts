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

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async headers() {
    return [{ source: "/forms/:slug", headers: [{ key: "Content-Security-Policy", value: publicPageCsp }] }];
  },
};

export default nextConfig;
