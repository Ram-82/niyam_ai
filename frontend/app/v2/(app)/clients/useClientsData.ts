"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";

/* ---------------------------- Backend types ---------------------------- */

export type ClientResponse = {
  id: string;
  trade_name: string;
  language: string;
  whatsapp_number: string | null;
};

export type CommandCenterRow = {
  client_id: string;
  client_name: string;
  gstin_profile_id: string;
  gstin: string;
  scheme: string;
  return_type: string;
  period: string;
  score: number | null;
  days_to_due_date: number | null;
  itc_at_risk_paise: number;
  blockers_count: number;
  blockers_ca: number;
  blockers_client: number;
  last_computed_at: string | null;
  filing_status: string | null;
};

export type CommandCenterResponse = {
  period: string;
  rows: CommandCenterRow[];
  summary: {
    total_rows: number;
    unfiled_count: number;
    filed_count: number;
    total_itc_at_risk_paise: number;
    high_risk_count: number;
    due_soon_count: number;
  };
};

export type CalendarRow = {
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  client_trade_name: string;
  scheme: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  due_date: string;
  days_out: number;
  filing_status: "draft" | "approved" | "filed" | null;
  reminders_sent: number;
};

export type CalendarResponse = {
  today: string;
  horizon_days: number;
  lookback_days: number;
  rows: CalendarRow[];
};

export type AuditRow = {
  id: string;
  firm_id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  diff: Record<string, unknown>;
  at: string;
  user_email: string | null;
};

/* ---------------------------- Enriched client ---------------------------- */

export type EnrichedClient = {
  id: string;
  trade_name: string;
  whatsapp_number: string | null;
  language: string;
  gstin: string | null;             // first gid observed for this client
  scheme: string | null;
  score: number | null;             // min across all gid × return_type
  amount_at_risk_paise: number;     // sum of itc_at_risk_paise
  blockers_count: number;           // sum
  next_due_days: number | null;     // min positive days_to_due among unfiled
  next_due_label: string | null;    // e.g. "GSTR-3B · in 7d"
  last_filed_at: string | null;     // max last_computed_at across filed rows
  filed_this_month: number;
  total_returns_tracked: number;
  status: "active" | "at_risk" | "overdue" | "onboarding";
};

function enrichClients(
  base: ClientResponse[],
  cc: CommandCenterResponse | null,
): EnrichedClient[] {
  const byClient = new Map<string, CommandCenterRow[]>();
  if (cc) {
    for (const r of cc.rows) {
      if (!byClient.has(r.client_id)) byClient.set(r.client_id, []);
      byClient.get(r.client_id)!.push(r);
    }
  }

  return base.map((c) => {
    const rows = byClient.get(c.id) ?? [];
    if (rows.length === 0) {
      return {
        id: c.id,
        trade_name: c.trade_name,
        whatsapp_number: c.whatsapp_number,
        language: c.language,
        gstin: null,
        scheme: null,
        score: null,
        amount_at_risk_paise: 0,
        blockers_count: 0,
        next_due_days: null,
        next_due_label: null,
        last_filed_at: null,
        filed_this_month: 0,
        total_returns_tracked: 0,
        status: "onboarding",
      };
    }
    const gstin = rows[0].gstin;
    const scheme = rows[0].scheme;
    const scoredRows = rows.filter((r) => r.score !== null);
    const score = scoredRows.length
      ? Math.min(...scoredRows.map((r) => r.score as number))
      : null;
    const amountAtRisk = rows.reduce((s, r) => s + r.itc_at_risk_paise, 0);
    const blockers = rows.reduce((s, r) => s + r.blockers_count, 0);
    const unfiled = rows.filter((r) => r.filing_status !== "filed");
    const upcomingDays = unfiled
      .map((r) => r.days_to_due_date)
      .filter((d): d is number => d !== null && d >= 0);
    const nextDueDays = upcomingDays.length ? Math.min(...upcomingDays) : null;
    const nextDueRow = nextDueDays !== null
      ? unfiled.find((r) => r.days_to_due_date === nextDueDays) ?? null
      : null;

    const filed = rows.filter((r) => r.filing_status === "filed");
    const lastFiledAt = filed
      .map((r) => r.last_computed_at)
      .filter((v): v is string => !!v)
      .sort()
      .pop() ?? null;

    let status: EnrichedClient["status"] = "active";
    if (blockers > 0 || (score !== null && score < 60)) status = "at_risk";
    const anyOverdue = unfiled.some(
      (r) => r.days_to_due_date !== null && r.days_to_due_date < 0,
    );
    if (anyOverdue) status = "overdue";

    return {
      id: c.id,
      trade_name: c.trade_name,
      whatsapp_number: c.whatsapp_number,
      language: c.language,
      gstin,
      scheme,
      score,
      amount_at_risk_paise: amountAtRisk,
      blockers_count: blockers,
      next_due_days: nextDueDays,
      next_due_label: nextDueRow
        ? `${prettyReturnType(nextDueRow.return_type)} · ${describeDays(nextDueRow.days_to_due_date)}`
        : null,
      last_filed_at: lastFiledAt,
      filed_this_month: filed.length,
      total_returns_tracked: rows.length,
      status,
    };
  });
}

/* ---------------------------- Hooks ---------------------------- */

export type ClientsState = {
  clients: EnrichedClient[] | null;
  calendar: CalendarResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useClientsData(): ClientsState {
  const [base, setBase] = useState<ClientResponse[] | null>(null);
  const [cc, setCc] = useState<CommandCenterResponse | null>(null);
  const [cal, setCal] = useState<CalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      api<ClientResponse[]>("/clients"),
      api<CommandCenterResponse>("/command-center"),
      api<CalendarResponse>("/calendar/upcoming?horizon_days=180&lookback_days=30"),
    ]).then((results) => {
      if (cancelled) return;
      const [b, c, k] = results;
      setBase(b.status === "fulfilled" ? b.value : null);
      setCc(c.status === "fulfilled" ? c.value : null);
      setCal(k.status === "fulfilled" ? k.value : null);
      const firstErr = results.find((r) => r.status === "rejected") as
        | PromiseRejectedResult
        | undefined;
      if (firstErr) {
        const reason = firstErr.reason;
        setError(
          reason instanceof ApiError
            ? `${reason.status}: ${reason.message}`
            : String(reason?.message ?? reason),
        );
      }
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  const clients = useMemo(() => (base ? enrichClients(base, cc) : null), [base, cc]);

  return {
    clients,
    calendar: cal,
    loading,
    error,
    reload: () => setReloadKey((k) => k + 1),
  };
}

/** Lazy activity fetch for a selected client. */
export function useClientActivity(clientId: string | null) {
  const [items, setItems] = useState<AuditRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!clientId) {
      setItems(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api<AuditRow[]>(
      `/audit-log?entity_type=client&entity_id=${clientId}&limit=10`,
    )
      .then((rows) => { if (!cancelled) setItems(rows); })
      .catch((e) => {
        if (cancelled) return;
        setError(formatApiError(e));
        setItems([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [clientId]);

  return { items, loading, error };
}

/* ---------------------------- Derivations for the header + drawer ---------------------------- */

export function clientsStats(clients: EnrichedClient[] | null) {
  if (!clients) return { total: 0, active: 0, at_risk: 0, overdue: 0, healthPct: { compliant: 0, at_risk: 0, overdue: 0, onboarding: 0 } };
  let active = 0, atRisk = 0, overdue = 0, onboarding = 0;
  for (const c of clients) {
    if (c.status === "active") active++;
    else if (c.status === "at_risk") atRisk++;
    else if (c.status === "overdue") overdue++;
    else onboarding++;
  }
  const total = clients.length;
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0);
  return {
    total,
    active,
    at_risk: atRisk,
    overdue,
    healthPct: {
      compliant: pct(active),
      at_risk: pct(atRisk),
      overdue: pct(overdue),
      onboarding: pct(onboarding),
    },
  };
}

export function upcomingForClient(cal: CalendarResponse | null, clientId: string): CalendarRow[] {
  if (!cal) return [];
  return cal.rows
    .filter((r) => r.client_id === clientId && r.filing_status !== "filed")
    .sort((a, b) => a.days_out - b.days_out)
    .slice(0, 5);
}

/* ---------------------------- Formatters ---------------------------- */

export function prettyReturnType(rt: string): string {
  if (rt === "GSTR1") return "GSTR-1";
  if (rt === "GSTR3B") return "GSTR-3B";
  return rt;
}

export function prettyReturnBadge(rt: string): string {
  if (rt === "GSTR1") return "GST-1";
  if (rt === "GSTR3B") return "GST-3B";
  return rt;
}

export function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function formatPeriod(period: string): string {
  if (!/^[0-9]{6}$/.test(period)) return period;
  const year = period.slice(0, 4);
  const month = parseInt(period.slice(4), 10);
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month - 1] ?? "";
  return `${abbr} ${year}`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  });
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

export function describeDays(days: number | null): string {
  if (days === null) return "—";
  if (days < 0) return `overdue by ${Math.abs(days)}d`;
  if (days === 0) return "due today";
  return `in ${days}d`;
}

export function formatPaise(paise: number): { text: string; color: string; weight: number } {
  if (paise === 0) return { text: "—", color: "var(--text-muted)", weight: 400 };
  const rupees = paise / 100;
  const inr = `₹${rupees.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  if (rupees >= 500000) return { text: inr, color: "var(--danger)", weight: 500 };
  if (rupees >= 100000) return { text: inr, color: "var(--warning)", weight: 500 };
  return { text: inr, color: "var(--text-primary)", weight: 400 };
}

export function statusLabel(status: EnrichedClient["status"]) {
  switch (status) {
    case "active": return { label: "Active", tone: "success" as const };
    case "at_risk": return { label: "At risk", tone: "warning" as const };
    case "overdue": return { label: "Overdue", tone: "danger" as const };
    case "onboarding": return { label: "Onboarding", tone: "accent" as const };
  }
}

export function humanizeAction(action: string): string {
  const parts = action.replace(".", " ").replace(/_/g, " ").split(" ");
  if (parts.length === 0) return action;
  return parts[0][0].toUpperCase() + parts[0].slice(1) + (parts.length > 1 ? " " + parts.slice(1).join(" ") : "");
}
