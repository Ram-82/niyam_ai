"use client";

import { useEffect, useState } from "react";
import { api, apiBlob, ApiError } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";

/* ---------------------------- Backend types ---------------------------- */

export type NarrationRunRow = {
  id: string;
  gstin_profile_id: string;
  return_type: "GSTR1" | "GSTR3B" | string;
  period: string;
  language: string;
  provider: string;
  model: string;
  generated_at: string;
};

/* ---------------------------- Hook ---------------------------- */

export type NarratorState = {
  runs: NarrationRunRow[] | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useNarratorRuns(): NarratorState {
  const [runs, setRuns] = useState<NarrationRunRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api<NarrationRunRow[]>("/narrator/runs?limit=50")
      .then((r) => { if (!cancelled) setRuns(r); })
      .catch((e) => {
        if (cancelled) return;
        setError(formatApiError(e));
        setRuns(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  return { runs, loading, error, reload: () => setReloadKey((k) => k + 1) };
}

/* ---------------------------- PDF download ---------------------------- */

export async function downloadNarrationPdf(runId: string): Promise<void> {
  const blob = await apiBlob(`/narrator/runs/${runId}/pdf`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `narration-${runId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ---------------------------- Derivations ---------------------------- */

export type ConvoItem = {
  id: string;
  title: string;
  preview: string;
  active?: boolean;
  run: NarrationRunRow;
};

export type ConvoGroup = { label: string; items: ConvoItem[] };

export function groupRuns(runs: NarrationRunRow[], activeId: string | null): ConvoGroup[] {
  const now = Date.now();
  const buckets: Record<"today" | "week" | "earlier", ConvoItem[]> = {
    today: [],
    week: [],
    earlier: [],
  };
  for (const r of runs) {
    const then = new Date(r.generated_at).getTime();
    const diffDays = (now - then) / (1000 * 60 * 60 * 24);
    const item: ConvoItem = {
      id: r.id,
      title: `${prettyReturnType(r.return_type)} · ${formatPeriod(r.period)}`,
      preview: `${r.provider} · ${r.model} · ${r.language.toUpperCase()}`,
      active: r.id === activeId,
      run: r,
    };
    if (diffDays < 1) buckets.today.push(item);
    else if (diffDays < 7) buckets.week.push(item);
    else buckets.earlier.push(item);
  }
  const out: ConvoGroup[] = [];
  if (buckets.today.length) out.push({ label: "Today", items: buckets.today });
  if (buckets.week.length) out.push({ label: "This week", items: buckets.week });
  if (buckets.earlier.length) out.push({ label: "Earlier", items: buckets.earlier });
  return out;
}

/* ---------------------------- Formatters ---------------------------- */

export function prettyReturnType(rt: string): string {
  if (rt === "GSTR1") return "GSTR-1";
  if (rt === "GSTR3B") return "GSTR-3B";
  return rt;
}

export function formatPeriod(period: string): string {
  if (!/^[0-9]{6}$/.test(period)) return period;
  const year = period.slice(0, 4);
  const month = parseInt(period.slice(4), 10);
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month - 1] ?? "";
  return `${abbr} ${year}`;
}

export function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(1, Math.floor((now - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  return `${Math.floor(h / 24)}d ago`;
}
