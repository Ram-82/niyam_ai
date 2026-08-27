"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";

/* ---------------------------- Types ---------------------------- */

export type CalendarRow = {
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  client_trade_name: string;
  scheme: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  due_date: string; // ISO YYYY-MM-DD
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

export type EventTone = "success" | "warning" | "danger" | "accent" | "neutral";

export type CalendarCell = {
  day: number;
  isoDate: string;
  muted?: boolean;
  weekend?: boolean;
  today?: boolean;
  events: {
    key: string;
    badge: string;
    label: string;
    tone: EventTone;
    rows: CalendarRow[];
  }[];
  more?: number;
};

export type RailGroup = {
  label: string;
  active?: boolean;
  isoDate: string;
  rows: CalendarRow[];
};

/* ---------------------------- Hook ---------------------------- */

export type CalendarState = {
  data: CalendarResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useCalendarData(opts: { horizonDays?: number; lookbackDays?: number } = {}): CalendarState {
  const { horizonDays = 90, lookbackDays = 30 } = opts;
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api<CalendarResponse>(
      `/calendar/upcoming?horizon_days=${horizonDays}&lookback_days=${lookbackDays}`,
    )
      .then((r) => { if (!cancelled) setData(r); })
      .catch((e) => {
        if (cancelled) return;
        setError(formatApiError(e));
        setData(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [horizonDays, lookbackDays, reloadKey]);

  return { data, loading, error, reload: () => setReloadKey((k) => k + 1) };
}

/* ---------------------------- Derivations ---------------------------- */

const RETURN_BADGE: Record<string, string> = {
  GSTR1: "GST-1",
  GSTR3B: "GST-3B",
};

export function prettyReturnBadge(rt: string): string {
  return RETURN_BADGE[rt] ?? rt;
}

/** Aggregate rows into event pills for one day. Groups by
 *  (return_type, tone) and produces a "GST-1 due · 5" style label. */
function eventsForDay(rows: CalendarRow[], today: string): CalendarCell["events"] {
  if (rows.length === 0) return [];
  type Bucket = { rt: string; tone: EventTone; rows: CalendarRow[] };
  const groups = new Map<string, Bucket>();
  for (const r of rows) {
    const filed = r.filing_status === "filed";
    const overdue = !filed && r.due_date < today;
    const tone: EventTone = filed ? "success" : overdue ? "danger" : "warning";
    const key = `${r.return_type}:${tone}`;
    if (!groups.has(key)) groups.set(key, { rt: r.return_type, tone, rows: [] });
    groups.get(key)!.rows.push(r);
  }
  const out: CalendarCell["events"] = [];
  for (const g of groups.values()) {
    const verb = g.tone === "success" ? "filed" : g.tone === "danger" ? "overdue" : "due";
    const label =
      g.rows.length === 1
        ? `${g.rows[0].client_trade_name} — ${verb}`
        : `${g.rows.length} clients · ${verb}`;
    out.push({
      key: `${g.rt}:${g.tone}`,
      badge: prettyReturnBadge(g.rt),
      label,
      tone: g.tone,
      rows: g.rows,
    });
  }
  return out;
}

/** Build a 6-row Mon-start grid for `targetDate`'s month. Rows outside
 *  the target month are muted. Cells contain aggregated event pills. */
export function buildMonthGrid(
  rows: CalendarRow[],
  today: string,
  targetDate: Date,
): CalendarCell[] {
  const year = targetDate.getUTCFullYear();
  const month = targetDate.getUTCMonth();
  const first = new Date(Date.UTC(year, month, 1));
  const monStart = (first.getUTCDay() + 6) % 7; // Mon=0
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const prevDays = new Date(Date.UTC(year, month, 0)).getUTCDate();

  const byDay = new Map<string, CalendarRow[]>();
  for (const r of rows) {
    if (!byDay.has(r.due_date)) byDay.set(r.due_date, []);
    byDay.get(r.due_date)!.push(r);
  }

  const cells: CalendarCell[] = [];

  // Leading prev-month cells.
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
    const allEvents = eventsForDay(byDay.get(iso) ?? [], today);
    cells.push({
      day,
      isoDate: iso,
      weekend: isWeekend,
      today: iso === today,
      events: allEvents.slice(0, 3),
      ...(allEvents.length > 3 ? { more: allEvents.length - 3 } : {}),
    });
  }

  // Trailing next-month cells to reach 42.
  const remaining = 42 - cells.length;
  for (let day = 1; day <= remaining; day++) {
    const iso = isoFor(year, month + 1, day);
    cells.push({ day, isoDate: iso, muted: true, events: [] });
  }
  return cells;
}

function isoFor(year: number, month: number, day: number): string {
  return new Date(Date.UTC(year, month, day)).toISOString().slice(0, 10);
}

/** Rail: unfiled rows with 0 ≤ days_out ≤ 7, grouped by due_date. */
export function buildRailGroups(rows: CalendarRow[], today: string): RailGroup[] {
  const upcoming = rows.filter(
    (r) => r.filing_status !== "filed" && r.days_out >= 0 && r.days_out <= 7,
  );
  const byDay = new Map<string, CalendarRow[]>();
  for (const r of upcoming) {
    if (!byDay.has(r.due_date)) byDay.set(r.due_date, []);
    byDay.get(r.due_date)!.push(r);
  }
  const groups: RailGroup[] = [];
  for (const [iso, rs] of byDay) {
    groups.push({
      isoDate: iso,
      label: relativeDateLabel(iso, today),
      active: iso === today,
      rows: rs.sort((a, b) => a.client_trade_name.localeCompare(b.client_trade_name)),
    });
  }
  return groups.sort((a, b) => a.isoDate.localeCompare(b.isoDate));
}

function relativeDateLabel(iso: string, today: string): string {
  const then = new Date(iso);
  const now = new Date(today);
  const days = Math.round(
    (then.getTime() - now.getTime()) / (1000 * 60 * 60 * 24),
  );
  const weekday = then.toLocaleDateString("en-IN", {
    weekday: "short", day: "numeric", month: "short",
  });
  if (days === 0) return `Today · ${weekday}`;
  if (days === 1) return `Tomorrow · ${weekday}`;
  return weekday;
}

/* ---------------------------- Formatters ---------------------------- */

export function formatPeriod(period: string): string {
  if (!/^[0-9]{6}$/.test(period)) return period;
  const year = period.slice(0, 4);
  const month = parseInt(period.slice(4), 10);
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month - 1] ?? "";
  return `${abbr} ${year}`;
}

export function prettyReturnType(rt: string): string {
  if (rt === "GSTR1") return "GSTR-1";
  if (rt === "GSTR3B") return "GSTR-3B";
  return rt;
}

export function formatDueDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

export function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/** Stable status label for popover / rail card. */
export function statusForRow(row: CalendarRow): { label: string; tone: EventTone } {
  if (row.filing_status === "filed") return { label: "Filed", tone: "success" };
  if (row.filing_status === "approved") return { label: "Approved · not filed", tone: "accent" };
  if (row.days_out < 0) return { label: `Overdue · ${Math.abs(row.days_out)}d`, tone: "danger" };
  if (row.days_out === 0) return { label: "Due today", tone: "warning" };
  if (row.days_out <= 3) return { label: `Due in ${row.days_out}d`, tone: "warning" };
  return { label: `Due in ${row.days_out}d`, tone: "neutral" };
}

/** Compute how many rows fall in the visible month for a KPI header. */
export function useMonthStats(rows: CalendarRow[] | undefined, targetDate: Date) {
  return useMemo(() => {
    if (!rows) return { total: 0, overdue: 0, due_soon: 0, filed: 0 };
    const y = targetDate.getUTCFullYear();
    const m = targetDate.getUTCMonth();
    let total = 0, overdue = 0, dueSoon = 0, filed = 0;
    for (const r of rows) {
      const d = new Date(r.due_date);
      if (d.getUTCFullYear() !== y || d.getUTCMonth() !== m) continue;
      total++;
      if (r.filing_status === "filed") filed++;
      else if (r.days_out < 0) overdue++;
      else if (r.days_out <= 7) dueSoon++;
    }
    return { total, overdue, due_soon: dueSoon, filed };
  }, [rows, targetDate]);
}
