export type Field = { id: string; label: string; type: string; required?: boolean; options?: string[]; scale?: number };
export type Campaign = { id: string; name: string; slug: string; description: string; kind: string; status: string; visibility: string; fields: Field[]; thank_you: Record<string, string>; visits: number; responses: number; conversion: number; archived: boolean; created_at: string; updated_at: string };
export type Stats = { campaigns: number; active: number; responses: number; week_responses: number; conversion: number; daily: { date: string; count: number }[]; sources: { name: string; count: number }[]; recent: { id: string; campaign: string; name: string; source: string; created_at: string }[] };
export type Me = { id: string; email: string; full_name: string; role: string; company: { id: string; name: string; legal_name: string; sector: string; siret: string; address: string; primary_color: string; accent_color: string; tone: string; dpo_email: string } };

