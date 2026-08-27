import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sillage — Des formulaires qui avancent",
  description: "Créez, diffusez et analysez vos campagnes de formulaires.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}

