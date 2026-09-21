"use client";

import { PageHeader } from "@/components/shell";
import { ResponsesInbox } from "@/components/responses-inbox";

export default function ResponsesPage() {
  return <div className="page-wrap">
    <PageHeader eyebrow="COLLECTE" title="Réponses" description="Toutes les réponses de vos formulaires, filtrables et exportables."/>
    <ResponsesInbox/>
  </div>;
}
