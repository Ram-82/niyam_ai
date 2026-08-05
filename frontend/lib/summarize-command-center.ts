/**
 * Command-center summary aggregation.
 *
 * The command_center API returns ONE row per (client × GSTIN × return_type).
 * For a single (gstin_profile, period) the reconciliation summary is shared
 * across both return_type rows (GSTR1 + GSTR3B) — so summing ``itc_at_risk_paise``
 * across table rows double-counts the recon paise pool.
 *
 * The four tiles have DIFFERENT aggregation bases; each is documented on
 * the returned field so drift can't happen silently.
 */
import type { CommandCenterRow } from "./types";


export interface CommandCenterSummary {
  /** Aggregation basis: table-row count (client × GSTIN × return_type). */
  totalReturns: number;
  /** Aggregation basis: mean of non-null scores across table rows. Rounded to nearest int. Null when no row has a score. */
  avgScore: number | null;
  /** Aggregation basis: unique (gstin_profile_id, period) recon-summary paise — deduped across return_type rows because both rows for the same gstin+period share one recon run. */
  totalItcAtRiskPaise: number;
  /** Aggregation basis: table-row count where days_to_due < 0 (each return_type has its own due date; overdue GSTR1 and overdue GSTR3B are separate). */
  overdueReturns: number;
}


export function summarizeRows(rows: CommandCenterRow[]): CommandCenterSummary {
  const scores = rows
    .map((r) => r.score)
    .filter((s): s is number => s !== null);
  const avgScore = scores.length
    ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
    : null;

  // ITC dedup: one recon summary per (gstin_profile_id, period). The
  // API surface splits by return_type, but a single recon run drives
  // itc_at_risk_paise on both — sum by unique key, not per row.
  const seenItc = new Map<string, number>();
  for (const r of rows) {
    const key = `${r.gstin_profile_id}|${r.period}`;
    if (!seenItc.has(key)) seenItc.set(key, r.itc_at_risk_paise || 0);
  }
  const totalItcAtRiskPaise = [...seenItc.values()].reduce((a, b) => a + b, 0);

  const overdueReturns = rows.filter(
    (r) => r.days_to_due_date !== null && r.days_to_due_date < 0
  ).length;

  return {
    totalReturns: rows.length,
    avgScore,
    totalItcAtRiskPaise,
    overdueReturns,
  };
}
