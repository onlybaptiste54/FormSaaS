import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sillage — Tunnels de vente assistés par Luna",
  description: "Créez, diffusez et analysez vos tunnels de vente.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}

