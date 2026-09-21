"use client";

import { LoaderCircle, TriangleAlert } from "lucide-react";

export function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "green" | "amber" | "neutral" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function EmptyState({ icon, title, text, action }: { icon: React.ReactNode; title: string; text: string; action?: React.ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{text}</p>{action}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="empty-state"><div className="empty-icon error"><TriangleAlert /></div><h3>Chargement impossible</h3><p>{message}</p><button className="button button-secondary" onClick={onRetry}>Réessayer</button></div>;
}

export function Loading() {
  return <div className="loading"><LoaderCircle size={26} /><span>Chargement…</span></div>;
}

export function Toast({ children }: { children: React.ReactNode }) {
  return <div className="library-toast">{children}</div>;
}
