/**
 * Convert a ``Retry-After: <seconds>`` value to a wall-clock time in the
 * browser's local timezone and locale (e.g. "3:47 PM"). Used by every
 * user-visible 429 message — see ``RATE_LIMIT_COPY`` in
 * ``lib/constants.ts``.
 *
 * ``now`` is injectable so tests are deterministic. Production callers
 * omit it and get the browser's ``Date.now()``.
 */
export function formatRetryAt(
  retryAfterSeconds: number,
  now: Date = new Date()
): string {
  const at = new Date(now.getTime() + retryAfterSeconds * 1000);
  // Browser locale + browser timezone. No IST hardcode — a CA travelling
  // (or a non-India user someday) sees the wall-clock time on their own
  // clock, not on the server's.
  return at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}


/**
 * Convert an ISO timestamp to a browser-local wall-clock string.
 * Used by the P2.1 Stage E failure-surface copy to render
 * ``next_retry_at`` on a ``gsp_pull_attempt``.
 *
 * Returns null when ``iso`` is null/empty/unparseable so callers can
 * drop the "at X" clause cleanly.
 */
export function formatIsoAsLocalTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (isNaN(at.getTime())) return null;
  return at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
