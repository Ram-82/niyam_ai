/**
 * Indian-context date + period formatters.
 *
 * The stored/serialized forms stay canonical (ISO for dates, YYYYMM
 * for periods) — the API layer never sees these transforms. These are
 * DISPLAY-ONLY helpers the UI applies at the last mile.
 *
 * Rules:
 *   dates   -> DD-MM-YYYY everywhere ("15-06-2026")
 *   periods -> "MMM YYYY"           ("Jun 2026")
 */

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];


/**
 * ``formatDateIN("2026-06-15")`` → ``"15-06-2026"``.
 * ``formatDateIN(undefined | null | "")`` → ``"—"``.
 * Accepts either ISO ``YYYY-MM-DD`` or a full ISO 8601 timestamp
 * (uses the date portion).
 */
export function formatDateIN(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const src = typeof input === "string" ? input.slice(0, 10) : input.toISOString().slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(src);
  if (!m) return String(input);
  return `${m[3]}-${m[2]}-${m[1]}`;
}


/**
 * ``formatPeriod("202607")`` → ``"Jul 2026"``.
 * ``formatPeriod("2026-07")`` → ``"Jul 2026"`` (also accepts hyphenated).
 * ``formatPeriod(null | "")`` → ``"—"``.
 * Never touches the stored string — the API still sends ``YYYYMM``.
 */
export function formatPeriod(period: string | null | undefined): string {
  if (!period) return "—";
  const cleaned = period.replace(/-/g, "");
  if (!/^\d{6}$/.test(cleaned)) return period;
  const year = cleaned.slice(0, 4);
  const monthIdx = parseInt(cleaned.slice(4, 6), 10) - 1;
  if (monthIdx < 0 || monthIdx > 11) return period;
  return `${MONTH_ABBR[monthIdx]} ${year}`;
}


/**
 * Compact ISO timestamp for the "computed at" caption on snapshots.
 * ``"2026-07-14T11:23:00Z"`` → ``"14-07-2026 11:23"`` in Asia/Kolkata.
 * Falls back to the raw string if parsing fails.
 */
export function formatTimestampIN(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const d = typeof input === "string" ? new Date(input) : input;
  if (isNaN(d.getTime())) return String(input);
  // Force IST via the Intl API; keep display 24-hour to match ledger norm.
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const g = (k: string) => parts.find((p) => p.type === k)?.value ?? "";
  return `${g("day")}-${g("month")}-${g("year")} ${g("hour")}:${g("minute")}`;
}
