"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, BookOpen, ChevronDown, CircleHelp, FileText, LayoutDashboard, LogOut, Menu, Plus, Settings, Users, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Logo } from "./logo";

const items = [
  { href: "/dashboard", label: "Vue d’ensemble", icon: LayoutDashboard },
  { href: "/campaigns", label: "Campagnes", icon: FileText },
  { href: "/responses", label: "Réponses", icon: BarChart3 },
  { href: "/library", label: "Bibliothèque", icon: BookOpen },
  { href: "/team", label: "Équipe", icon: Users },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api<Me>("/me").then(setMe).catch(() => router.replace("/"));
  }, [router]);

  function logout() { localStorage.removeItem("sillage_token"); router.replace("/"); }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="sidebar-head"><Logo /><button className="icon-button sidebar-close" onClick={() => setOpen(false)} aria-label="Fermer"><X size={20} /></button></div>
        <Link href="/campaigns/new" className="button button-primary sidebar-create"><Plus size={18} />Nouvelle campagne</Link>
        <nav className="main-nav">
          {items.map(({ href, label, icon: Icon }) => <Link key={href} href={href} onClick={() => setOpen(false)} className={pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`)) ? "nav-item active" : "nav-item"}><Icon size={19} /><span>{label}</span></Link>)}
        </nav>
        <div className="sidebar-bottom">
          <Link href="/settings" className={`nav-item ${pathname === "/settings" ? "active" : ""}`}><Settings size={19} /><span>Paramètres</span></Link>
          <a href="mailto:aide@sillage.fr" className="nav-item"><CircleHelp size={19} /><span>Centre d’aide</span></a>
          <div className="account-card">
            <div className="avatar">{me?.full_name.split(" ").map(v => v[0]).join("").slice(0, 2) || "CM"}</div>
            <div><strong>{me?.full_name || "Camille Martin"}</strong><small>{me?.company.name || "Atelier Rivage"}</small></div>
            <button className="icon-button" onClick={logout} aria-label="Se déconnecter"><LogOut size={17} /></button>
          </div>
        </div>
      </aside>
      {open && <button className="sidebar-overlay" onClick={() => setOpen(false)} aria-label="Fermer le menu" />}
      <main className="main-content">
        <div className="mobile-topbar"><button className="icon-button" onClick={() => setOpen(true)}><Menu size={22} /></button><Logo /><div className="avatar avatar-small">CM</div></div>
        {children}
      </main>
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: React.ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</header>;
}

