"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";

/* ---------------------------- Backend types ---------------------------- */

export type FilingListRow = {
  id: string;
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  client_name: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  status: "draft" | "approved" | "filed";
  updated_at: string;
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
  rows: unknown[];
  summary: CommandCenterSummary;
};

export type FirmHealthSummary = {
  score: number | null;
  prev_score: number | null;
  active_clients_count: number;
  distribution: { healthy: number; due_soon: number; overdue_blocked: number };
  last_computed_at: string | null;
};

export type MonthlyTimeliness = {
  period: string;
  label: string;
  gstr1_filed: number;
  gstr1_on_time: number;
  gstr3b_filed: number;
  gstr3b_on_time: number;
};

export type TimelinessResponse = {
  period_from: string;
  period_to: string;
  months: MonthlyTimeliness[];
  total_filed: number;
  total_on_time: number;
};

/* ---------------------------- Derived shapes ---------------------------- */

export type MonthlyStack = {
  period: string;             // YYYYMM
  label: string;              // "Aug"
  gstr1: number;
  gstr3b: number;
  other: number;
  total: number;
};

export type ReportsKpi = {
  label: string;
  value: string;
  delta: string;
  deltaTone: "success" | "danger" | "accent" | "neutral";
  spark: number[];
  sparkTone: "success" | "danger" | "accent" | "warning";
};

/* ---------------------------- Hook ---------------------------- */

export type ReportsState = {
  cc: CommandCenterResponse | null;
  health: FirmHealthSummary | null;
  filings: FilingListRow[] | null;
  timeliness: TimelinessResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useReportsData(): ReportsState {
  const [cc, setCc] = useState<CommandCenterResponse | null>(null);
  const [health, setHealth] = useState<FirmHealthSummary | null>(null);
  const [filings, setFilings] = useState<FilingListRow[] | null>(null);
  const [timeliness, setTimeliness] = useState<TimelinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      api<CommandCenterResponse>("/command-center"),
      api<FirmHealthSummary>("/firm/health-summary"),
      api<FilingListRow[]>("/filings?limit=200"),
      api<TimelinessResponse>("/reports/timeliness"),
    ]).then((results) => {
      if (cancelled) return;
      const [c, h, f, t] = results;
      setCc(c.status === "fulfilled" ? c.value : null);
      setHealth(h.status === "fulfilled" ? h.value : null);
      setFilings(f.status === "fulfilled" ? f.value : null);
      setTimeliness(t.status === "fulfilled" ? t.value : null);
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

  return {
    cc, health, filings, timeliness,
    loading, error,
    reload: () => setReloadKey((k) => k + 1),
  };
}

/* ---------------------------- Derivations ---------------------------- */

/** Enumerate the last N periods ending in `now` (inclusive). */
function last_n_periods(now: Date, n: number): { period: string; label: string; date: Date }[] {
  const out: { period: string; label: string; date: Date }[] = [];
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
    const y = d.getUTCFullYear();
    const m = d.getUTCMonth() + 1;
    out.push({
      period: `${y}${String(m).padStart(2, "0")}`,
      label: abbr[m - 1],
      date: d,
    });
  }
  return out;
}

/** Group filings by period + return_type. Only 'filed' status counts —
 *  drafts/approved aren't yet in the throughput metric. */
export function buildMonthlyStacks(
  filings: FilingListRow[] | null,
  monthsBack: number = 12,
): MonthlyStack[] {
  const periods = last_n_periods(new Date(), monthsBack);
  const byPeriod = new Map<string, { gstr1: number; gstr3b: number; other: number }>();
  if (filings) {
    for (const f of filings) {
      if (f.status !== "filed") continue;
      if (!byPeriod.has(f.period)) byPeriod.set(f.period, { gstr1: 0, gstr3b: 0, other: 0 });
      const b = byPeriod.get(f.period)!;
      if (f.return_type === "GSTR1") b.gstr1++;
      else if (f.return_type === "GSTR3B") b.gstr3b++;
      else b.other++;
    }
  }
  return periods.map((p) => {
    const b = byPeriod.get(p.period) ?? { gstr1: 0, gstr3b: 0, other: 0 };
    return {
      period: p.period,
      label: p.label,
      gstr1: b.gstr1,
      gstr3b: b.gstr3b,
      other: b.other,
      total: b.gstr1 + b.gstr3b + b.other,
    };
  });
}

/** Prior-period totals — same 12 windows shifted back by 12 months. */
export function buildPrevTotals(
  filings: FilingListRow[] | null,
  monthsBack: number = 12,
): number[] {
  const periods = last_n_periods(
    new Date(new Date().setUTCFullYear(new Date().getUTCFullYear() - 1)),
    monthsBack,
  );
  const byPeriod = new Map<string, number>();
  if (filings) {
    for (const f of filings) {
      if (f.status !== "filed") continue;
      byPeriod.set(f.period, (byPeriod.get(f.period) ?? 0) + 1);
    }
  }
  return periods.map((p) => byPeriod.get(p.period) ?? 0);
}

/** Sparkline data for the "Total filings" KPI — last 8 monthly totals. */
export function totalsSparkline(stacks: MonthlyStack[]): number[] {
  return stacks.slice(-8).map((s) => s.total);
}

export function computeKpis(
  cc: CommandCenterResponse | null,
  health: FirmHealthSummary | null,
  stacks: MonthlyStack[],
): ReportsKpi[] {
  const totalFiled = stacks.reduce((s, m) => s + m.total, 0);
  const prevMonth = stacks.length >= 2 ? stacks[stacks.length - 2].total : 0;
  const currentMonth = stacks.length >= 1 ? stacks[stacks.length - 1].total : 0;
  const totalDelta =
    prevMonth === 0
      ? currentMonth === 0
        ? "no history"
        : `+${currentMonth} vs 0`
      : `${currentMonth >= prevMonth ? "+" : ""}${(((currentMonth - prevMonth) / prevMonth) * 100).toFixed(1)}% vs prev`;
  const totalTone: ReportsKpi["deltaTone"] =
    prevMonth === 0 ? "neutral" : currentMonth >= prevMonth ? "success" : "danger";

  const onTimePct =
    cc && cc.summary.total_rows > 0
      ? (cc.summary.filed_count / cc.summary.total_rows) * 100
      : null;

  const atRiskCr =
    cc ? cc.summary.total_itc_at_risk_paise / 1_00_00_000 / 100 : 0;

  const spark = totalsSparkline(stacks);

  return [
    {
      label: "Total filings (12mo)",
      value: totalFiled.toLocaleString("en-IN"),
      delta: totalDelta,
      deltaTone: totalTone,
      spark: spark.length > 0 ? spark : [0, 0, 0, 0, 0, 0, 0, 0],
      sparkTone: totalTone === "danger" ? "danger" : "success",
    },
    {
      label: "On-time this period",
      value: onTimePct === null ? "—" : `${onTimePct.toFixed(1)}%`,
      delta: cc ? `${cc.summary.filed_count} / ${cc.summary.total_rows} filed` : "—",
      deltaTone: onTimePct === null ? "neutral" : onTimePct >= 90 ? "success" : "danger",
      spark: spark,
      sparkTone: onTimePct === null || onTimePct >= 90 ? "success" : "danger",
    },
    {
      label: "Firm compliance score",
      value: health?.score !== null && health?.score !== undefined ? `${health.score}/100` : "—",
      delta:
        health?.prev_score != null && health?.score != null
          ? `${health.score - health.prev_score >= 0 ? "+" : ""}${health.score - health.prev_score} vs prev`
          : "no history yet",
      deltaTone:
        health?.prev_score == null || health?.score == null
          ? "neutral"
          : health.score >= health.prev_score
          ? "success"
          : "danger",
      spark: spark,
      sparkTone: "accent",
    },
    {
      label: "ITC at risk (this period)",
      value: `₹${atRiskCr.toFixed(2)} Cr`,
      delta: cc ? `${cc.summary.high_risk_count} high-risk filings` : "—",
      deltaTone: atRiskCr > 0 ? "danger" : "success",
      spark: spark,
      sparkTone: atRiskCr > 0 ? "danger" : "success",
    },
  ];
}

export function monthsWindowLabel(): string {
  const periods = last_n_periods(new Date(), 12);
  if (periods.length === 0) return "—";
  const first = periods[0];
  const last = periods[periods.length - 1];
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${abbr[first.date.getUTCMonth()]} ${first.date.getUTCFullYear()} – ${abbr[last.date.getUTCMonth()]} ${last.date.getUTCFullYear()}`;
}
