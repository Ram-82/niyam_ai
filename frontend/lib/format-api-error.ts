/**
 * Convert a caught error into readable UI text.
 *
 * Every write surface in v2 used to render caught errors with
 * ``String(e)`` or ``e.message``. When the backend returned a structured
 * detail (e.g. ``{"detail": {"error": "legal_acceptance_required", ...}}``)
 * that came out as ``[object Object]`` on the screen. This helper is
 * the one place that translates ``ApiError`` — and ordinary Errors — into
 * something a user can act on.
 *
 * Design notes:
 *   * Known machine-readable codes get a specific message.
 *   * Unknown failures render as ``<factual status> · req <requestId>``
 *     — never a bare object, never an empty string.
 *   * Non-``ApiError`` throwables are still handled (network drop,
 *     TypeError from a JSON parse) so the callers don't need branching.
 */
import { ApiError } from "./api";


/**
 * Human-facing text for machine-readable ``code`` slugs the backend
 * hands back inside ``{"detail": {"error": "...", ...}}``.
 *
 * When adding a code, prefer a factual imperative — tell the user what
 * to do next, not what went wrong. If you cannot honestly say what to
 * do, leave the code out; the generic fallback is better than a
 * false-reassurance message.
 */
const CODE_MESSAGES: Record<string, string> = {
  legal_acceptance_required:
    "You need to accept the current Terms and Data Processing Addendum before your firm can add or import client data.",
};


export function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code && CODE_MESSAGES[err.code]) {
      return CODE_MESSAGES[err.code];
    }
    const status = `${err.status} ${err.message}`.trim();
    if (err.requestId) {
      return `${status} · req ${err.requestId}`;
    }
    return status;
  }
  if (err instanceof Error) {
    // Ordinary Error: message is a string by construction, so it's
    // safe. Guard against an empty string.
    return err.message || err.name || "Unknown error";
  }
  if (typeof err === "string") {
    return err;
  }
  // Anything else — a bare object, null, undefined — degrades to a
  // safe placeholder rather than "[object Object]".
  return "Unknown error";
}
