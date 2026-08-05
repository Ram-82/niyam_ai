/**
 * Days-to-due display mapping.
 *
 * The single most urgent state in the product is "overdue" — the
 * raw negative number that used to leak to the UI ("-9") was a
 * usability bug. This mapping enforces the correct rendering:
 *
 *   null    -> "—"           plain
 *   > 3     -> "9"           plain number
 *   1 – 3   -> "3 days"      amber pill
 *   0       -> "Due today"   red pill
 *   < 0     -> "Overdue 9d"  red pill
 *
 * Sort semantics DO NOT change — callers keep sorting on the raw
 * number, which puts overdue at the top when ascending.
 */

export type DaysTone = "plain" | "amber-pill" | "red-pill" | "empty";

export function formatDaysToDue(days: number | null): { label: string; tone: DaysTone } {
  if (days === null || days === undefined) return { label: "—", tone: "empty" };
  if (days < 0) return { label: `Overdue ${Math.abs(days)}d`, tone: "red-pill" };
  if (days === 0) return { label: "Due today", tone: "red-pill" };
  if (days <= 3) return { label: `${days} day${days === 1 ? "" : "s"}`, tone: "amber-pill" };
  return { label: `${days}`, tone: "plain" };
}
