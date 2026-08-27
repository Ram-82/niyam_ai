"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";

/* ---------------------------- Backend types ---------------------------- */

export type FirmHealthSummary = {
  score: number | null;
  prev_score: number | null;
  active_clients_count: number;
  distribution: {
    healthy: number;
    due_soon: number;
    overdue_blocked: number;
  };
  last_computed_at: string | null;
};

export type CalendarRow = {
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  client_trade_name: string;
  scheme: string;
  return_type: string;
  period: string;
  due_date: string;      // ISO YYYY-MM-DD
  days_out: number;      // negative = overdue
  filing_status: "draft" | "approved" | "filed" | null;
  reminders_sent: number;
};

export type CalendarResponse = {
  today: string;
  horizon_days: number;
  lookback_days: number;
  rows: CalendarRow[];
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

export type CommandCenterSummary = {
  total_rows: number;
  unfiled_count: number;
  filed_count: number;
  total_itc_at_risk_paise: number;
  high_risk_count: number;
  due_soon_count: number;
};

export type CommandCenterResponse = {
  period: string;
  rows: CommandCenterRow[];
  summary: CommandCenterSummary;
};

export type RecentActivityItem = {
  id: string;
  at: string;
  action: string;
  tone: "success" | "danger" | "neutral";
  icon: "check" | "alert" | "upload" | "message" | "settings";
  title: string;
  subtitle: string | null;
  actor_email: string | null;
};

/* ---------------------------- Hook ---------------------------- */

export type DashboardData = {
  health: FirmHealthSummary | null;
  calendar: CalendarResponse | null;
  commandCenter: CommandCenterResponse | null;
  activity: RecentActivityItem[] | null;
};

export type DashboardState = {
  data: DashboardData;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useDashboardData(): DashboardState {
  const [data, setData] = useState<DashboardData>({
    health: null,
    calendar: null,
    commandCenter: null,
    activity: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.allSettled([
      api<FirmHealthSummary>("/firm/health-summary"),
      api<CalendarResponse>("/calendar/upcoming?horizon_days=45&lookback_days=14"),
      api<CommandCenterResponse>("/command-center"),
      api<RecentActivityItem[]>("/firm/recent-activity?limit=6"),
    ])
      .then((results) => {
        if (cancelled) return;
        const [h, c, cc, a] = results;
        const firstErr = results.find((r) => r.status === "rejected") as
          | PromiseRejectedResult
          | undefined;
        setData({
          health: h.status === "fulfilled" ? h.value : null,
          calendar: c.status === "fulfilled" ? c.value : null,
          commandCenter: cc.status === "fulfilled" ? cc.value : null,
          activity: a.status === "fulfilled" ? a.value : null,
        });
        if (firstErr) {
          setError(formatApiError(firstErr.reason));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return {
    data,
    loading,
    error,
    reload: () => setReloadKey((k) => k + 1),
  };
}

/* ---------------------------- Derivations ---------------------------- */

export type CalendarCell = {
  day: number;
  isoDate: string;
  muted?: boolean;
  weekend?: boolean;
  today?: boolean;
  events: { label: string; tone: "success" | "warning" | "danger" | "neutral"; tip: string }[];
  more?: number;
};

/** Build a 6-row Mon-start month grid for `today`'s month, with events
 *  from calendar rows placed on their due-date cells. */
export function buildMonthGrid(cal: CalendarResponse | null): CalendarCell[] {
  if (!cal) return [];
  const today = new Date(cal.today);
  const year = today.getUTCFullYear();
  const month = today.getUTCMonth();
  const first = new Date(Date.UTC(year, month, 1));
  const monStart = (first.getUTCDay() + 6) % 7; // Mon=0
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const prevDays = new Date(Date.UTC(year, month, 0)).getUTCDate();

  // Bucket rows by ISO date.
  const byDay = new Map<string, CalendarRow[]>();
  for (const r of cal.rows) {
    const d = r.due_date;
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d)!.push(r);
  }

  const cells: CalendarCell[] = [];
  const todayIso = cal.today;

  // Leading prev-month muted cells.
  for (let i = monStart - 1; i >= 0; i--) {
    const day = prevDays - i;
    const iso = isoFor(year, month - 1, day);
    cells.push({ day, isoDate: iso, muted: true, events: [] });
  }

  // Current month.
  for (let day = 1; day <= daysInMonth; day++) {
    const iso = isoFor(year, month, day);
    const dow = new Date(Date.UTC(year, month, day)).getUTCDay();
    const isWeekend = dow === 0 || dow === 6;
    const rows = byDay.get(iso) ?? [];
    const events = summarizeDayEvents(rows);
    const isToday = iso === todayIso;
    cells.push({
      day,
      isoDate: iso,
      weekend: isWeekend,
      today: isToday,
      events: events.slice(0, 2),
      ...(events.length > 2 ? { more: events.length - 2 } : {}),
    });
  }

  // Trailing next-month muted cells to reach 6 rows × 7 cols = 42.
  const remaining = 42 - cells.length;
  for (let day = 1; day <= remaining; day++) {
    const iso = isoFor(year, month + 1, day);
    cells.push({ day, isoDate: iso, muted: true, events: [] });
  }
  return cells;
}

function isoFor(year: number, month: number, day: number): string {
  const d = new Date(Date.UTC(year, month, day));
  return d.toISOString().slice(0, 10);
}

function summarizeDayEvents(rows: CalendarRow[]): CalendarCell["events"] {
  if (rows.length === 0) return [];
  // Group by return_type + status bucket.
  const groups = new Map<
    string,
    { rt: string; tone: "success" | "warning" | "danger"; rows: CalendarRow[] }
  >();
  for (const r of rows) {
    const overdue = r.days_out < 0 && r.filing_status !== "filed";
    const filed = r.filing_status === "filed";
    const tone: "success" | "warning" | "danger" = filed
      ? "success"
      : overdue
      ? "danger"
      : "warning";
    const key = `${r.return_type}:${tone}`;
    if (!groups.has(key)) groups.set(key, { rt: r.return_type, tone, rows: [] });
    groups.get(key)!.rows.push(r);
  }
  const out: CalendarCell["events"] = [];
  for (const g of groups.values()) {
    const verb = g.tone === "success" ? "filed" : g.tone === "danger" ? "overdue" : "due";
    const label = `${prettyReturnType(g.rt)} ${verb} · ${g.rows.length}`;
    const tip = g.rows
      .slice(0, 3)
      .map((r) => r.client_trade_name)
      .join(", ") + (g.rows.length > 3 ? `, +${g.rows.length - 3} more` : "");
    out.push({ label, tone: g.tone, tip });
  }
  return out;
}

function prettyReturnType(rt: string): string {
  if (rt === "GSTR1") return "GSTR-1";
  if (rt === "GSTR3B") return "GSTR-3B";
  return rt;
}

/** Top N high-risk rows for the At-Risk section — already server-sorted
 *  (score ASC NULLS FIRST, days_to_due ASC). Filter out rows without a
 *  real signal so the table stays actionable. */
export function pickAtRiskRows(
  cc: CommandCenterResponse | null,
  limit = 6,
): CommandCenterRow[] {
  if (!cc) return [];
  return cc.rows
    .filter(
      (r) =>
        (r.score !== null && r.score < 60) ||
        r.blockers_count > 0 ||
        (r.days_to_due_date !== null && r.days_to_due_date <= 3) ||
        (r.filing_status !== "filed" && r.days_to_due_date !== null && r.days_to_due_date < 0),
    )
    .slice(0, limit);
}

/** Formatters used in the KPI + at-risk rendering. */
export function formatPaise(paise: number): string {
  const rupees = paise / 100;
  return `₹${rupees.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function formatDueDate(days: number | null): string {
  if (days === null) return "—";
  const now = new Date();
  const d = new Date(now);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDueStatus(
  days: number | null,
  filingStatus: string | null,
  blockersCount: number,
): { label: string; tone: "success" | "warning" | "danger" | "blocker" | "neutral" } {
  if (filingStatus === "filed") return { label: "Filed", tone: "success" };
  if (blockersCount > 0) return { label: "Blocker", tone: "blocker" };
  if (days === null) return { label: "No due date", tone: "neutral" };
  if (days < 0) return { label: `Overdue · ${Math.abs(days)}d`, tone: "danger" };
  if (days === 0) return { label: "Due today", tone: "warning" };
  if (days <= 3) return { label: `Due in ${days} day${days === 1 ? "" : "s"}`, tone: "warning" };
  return { label: `Due in ${days}d`, tone: "neutral" };
}

export function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(1, Math.floor((now - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function computeDistributionPct(d: FirmHealthSummary["distribution"]): {
  healthyPct: number;
  dueSoonPct: number;
  overduePct: number;
} {
  const total = d.healthy + d.due_soon + d.overdue_blocked;
  if (total === 0) return { healthyPct: 0, dueSoonPct: 0, overduePct: 0 };
  const healthyPct = Math.round((d.healthy / total) * 100);
  const overduePct = Math.round((d.overdue_blocked / total) * 100);
  const dueSoonPct = Math.max(0, 100 - healthyPct - overduePct);
  return { healthyPct, dueSoonPct, overduePct };
}
