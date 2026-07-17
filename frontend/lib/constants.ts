/**
 * Shared UI copy that must not drift.
 *
 * CDN_DISCLAIMER — Criterion #1: this string renders next to every
 * ITC figure in the app. Command center column tooltip, recon summary,
 * ITC drilldowns, blocker paise_impact fields — everywhere. When the
 * P2 CDN pipeline lands, we drop this constant AND update every
 * consumer in the same PR.
 */
export const CDN_DISCLAIMER = "Before credit/debit note adjustments";

/**
 * Bucket-name copy for reconciliation. The DB enum values are legacy
 * identifiers; the labels the CA sees are here, softened per
 * criterion #2.
 */
export const BUCKET_LABELS: Record<string, string> = {
  matched: "Matched",
  probable: "Probable — awaiting review",
  supplier_default: "No 2B match found",
  missing_entry: "Missing register entry (in 2B, not in register)",
};

export const BUCKET_DESCRIPTIONS: Record<string, string> = {
  matched: "Exact match with a 2B entry.",
  probable:
    "Fuzzy match above threshold. Confirm to promote to matched, or reject to move to residual.",
  supplier_default:
    "No 2B match found — could be a register-side error (typo/wrong period), a timing gap (supplier files later), or a genuine supplier default. Review near-misses before any supplier chase.",
  missing_entry:
    "2B entry with no register counterpart — likely an unrecorded purchase; record before filing.",
};

/**
 * The command-center default period is the last complete calendar
 * month (Asia/Kolkata). Server also computes this; front-end mirrors
 * so links / bookmarks work.
 */
export function defaultPeriod(now: Date = new Date()): string {
  const firstOfThisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastOfPrev = new Date(firstOfThisMonth.getTime() - 24 * 60 * 60 * 1000);
  const yyyy = lastOfPrev.getFullYear().toString().padStart(4, "0");
  const mm = (lastOfPrev.getMonth() + 1).toString().padStart(2, "0");
  return `${yyyy}${mm}`;
}
