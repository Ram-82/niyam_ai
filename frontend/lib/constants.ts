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
 * GSP connection reason → user-facing copy. The panel must render the
 * SPECIFIC stored cause (not a generic message) so the CA understands
 * what to say to the client. Vendor-side revocation and TTL expiry
 * imply different follow-up actions.
 */
export const GSP_RECONNECT_REASON: Record<string, string> = {
  consent_revoked:
    "Consent was revoked on the GSTN portal. Ask the client to reconnect from your side; the OTP will go to the GSTIN-registered mobile.",
  session_expired:
    "The GSP session TTL elapsed. Reconnect to refresh; the OTP goes to the GSTIN-registered mobile.",
  reconnect:
    "This connection was superseded by a newer one.",
  user_disconnected:
    "This GSTIN was manually disconnected from Niyam.",
};

/**
 * OTP flow reality: the OTP is sent to the MSME owner's mobile
 * (registered on the GSTIN with GSTN), NOT the CA's phone. The CA
 * calls the client and the client reads out the code. Every UI touch
 * point uses this exact copy so no CA is surprised.
 */
export const GSP_OTP_DELIVERY_COPY =
  "The one-time code goes to the mobile number registered on this GSTIN with GSTN. Call the client and have them read it out.";


/**
 * Rate-limit copy — every user-visible 429 renders through one of these
 * builders. The ``at`` argument is a wall-clock time string produced by
 * ``formatRetryAt`` (see ``lib/format-retry-after.ts``).
 *
 * Design rules (P2.1 Stage D):
 *   - state WHAT happened + WHEN it clears + brief WHY (if useful)
 *   - never push "contact support" as primary path
 *   - no blame, no reassurance-theatre
 *   - restyle allowed, reword frozen: shape-locked by
 *     ``rate-limit-copy.test.ts`` so a silent rewording breaks CI
 */
/**
 * Failed-pull reason copy (P2.1 Stage E). One entry per ``error_kind``
 * value that can land on a ``gsp_pull_attempt.error_kind`` field.
 *
 *   needs_action = false  → transient / auto-retry (amber chip, no CTA)
 *   needs_action = true   → CA action required (reconnect via existing button)
 *
 * ``next_retry_at`` is an optional wall-clock string; when present, the
 * copy appends " at ${next_retry_at}" so the CA sees when Niyam plans
 * to try again.
 *
 * Anti-drift shape-locked in ``failed-pull-reason.test.ts``.
 */
export const FAILED_PULL_REASON: Record<
  string,
  { needs_action: boolean; text: (opts: { next_retry_at?: string | null }) => string }
> = {
  gstn_unavailable: {
    needs_action: false,
    text: ({ next_retry_at }) =>
      next_retry_at
        ? `GSTN was unavailable on the last attempt. Niyam will retry automatically at ${next_retry_at}.`
        : "GSTN was unavailable on the last attempt. Niyam will retry automatically.",
  },
  rate_limited: {
    needs_action: false,
    text: ({ next_retry_at }) =>
      next_retry_at
        ? `GSP rate limit hit on the last attempt. Niyam will retry automatically at ${next_retry_at}.`
        : "GSP rate limit hit on the last attempt. Niyam will retry automatically.",
  },
  session_expired: {
    needs_action: true,
    text: () => "The GSP session had expired at the time of the last attempt.",
  },
  consent_revoked: {
    needs_action: true,
    text: () =>
      "Consent was revoked on the GSTN portal; the last attempt could not proceed.",
  },
  session_dead: {
    needs_action: true,
    text: () => "No live GSP session at the time of the last attempt.",
  },
  unknown: {
    needs_action: true,
    text: () =>
      "The last attempt failed with an unclassified error. Try Pull-now again; if it repeats, reconnect.",
  },
};


/**
 * Default when a ``gsp_pull_attempt.error_kind`` is present but not one
 * of the mapped values. Kept conservative — no speculation about cause.
 */
export const FAILED_PULL_REASON_DEFAULT = FAILED_PULL_REASON["unknown"];


export const RATE_LIMIT_COPY = {
  /** 429 from POST /gsp/consent — per-GSTIN SMS-flood cooldown, 3/hour. */
  otp_sms_cooldown: (at: string) =>
    `Next OTP request available at ${at}. Cap is 3 per GSTIN per hour to protect the registered mobile.`,

  /** 429 from POST /gsp/consent/confirm — OTP brute-force lockout, 5 fails / 15 min per (user, GSTIN). */
  otp_confirm_lockout: (at: string) =>
    `Five wrong OTPs on this GSTIN. Next attempt available at ${at}. A fresh OTP can be requested after that.`,

  /** 429 from POST /auth/login — per-email login lockout, 5 fails / 15 min. */
  login_lockout: (at: string) =>
    `Five failed sign-in attempts on this email. Try again at ${at}.`,
} as const;

/**
 * Delivery status → user-facing copy. Shape-locked: adding a status
 * requires a matching key here or the DeliveryPanel will render
 * "Unknown status", which is louder than silence but still bad UX.
 */
export const DELIVERY_STATUS_COPY: Record<
  string,
  { label: string; tone: "muted" | "ok" | "warn" | "bad" }
> = {
  queued: { label: "Queued", tone: "muted" },
  sent: { label: "Sent", tone: "ok" },
  delivered: { label: "Delivered", tone: "ok" },
  read: { label: "Read", tone: "ok" },
  failed: { label: "Failed", tone: "bad" },
};


/**
 * WhatsApp error kind → user-facing copy. Same shape-locked rules as
 * FAILED_PULL_REASON: state WHAT happened, WHY it's stuck, brief WHAT
 * to do. Never "contact support".
 */
export const WHATSAPP_ERROR_COPY: Record<string, string> = {
  template_not_approved:
    "The WhatsApp template for this message is not approved on the sender WABA. Submit or wait for Meta review before retrying.",
  invalid_number:
    "The destination number was rejected by WhatsApp. Verify the client's WhatsApp-enabled E.164 number and create a new delivery request.",
  rate_limited:
    "WhatsApp rate limit hit. Wait and retry with a new delivery request; back-to-back sends to the same number trip this.",
  meta_5xx:
    "WhatsApp's Cloud API returned a server error. Create a new delivery request and retry.",
  other:
    "Delivery failed with an unclassified error. Create a new delivery request and retry.",
};


/**
 * The narrator language codes as user-facing labels. Used in the
 * language select on the delivery preparation modal.
 */
export const NARRATION_LANGUAGE_LABELS: Record<string, string> = {
  en: "English",
  hi: "Hindi",
  kn: "Kannada",
  mr: "Marathi",
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
