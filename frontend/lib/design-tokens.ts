/**
 * TypeScript mirror of ``lib/tokens.css``. Import from here when a
 * component needs to reason about tokens programmatically (choosing
 * a colour based on a score, mapping a bucket to its chip class,
 * etc.). Anything you need at runtime lives here; anything the
 * cascade can handle lives in the CSS.
 */


// ---------------------------------------------------------------------------
// Palette — kept in sync with tokens.css by convention. If you edit one,
// edit both. There's no build-time cross-check; a grep for the hex
// during PR review is enough.
// ---------------------------------------------------------------------------


export const palette = {
  paper: "#F5F3EE",
  paperRaised: "#FFFFFF",
  ink: "#111319",
  inkMuted: "#4B5162",
  rule: "#D9D4C9",
  ruleStrong: "#B8B0A0",
  accent: "#1E3A5F",
  accentHover: "#142744",
  accentTint: "#E4E9F1",
  amberFg: "#92400E",
  amberBg: "#FEF3E2",
  amberStrong: "#B45309",
  redFg: "#991B1B",
  redBg: "#FDECEC",
  redStrong: "#B91C1C",
  greenFg: "#166534",
  greenBg: "#EAF5EB",
  greenStrong: "#15803D",
  greyFg: "#5A6070",
  greyBg: "#EDEBE5",
} as const;


// ---------------------------------------------------------------------------
// Score display bands.
//
// **UI-ONLY tuning.** These thresholds decide how the ScoreBadge
// renders (red / amber / green tint). They are NOT and MUST NOT be
// confused with any rule-pack thresholds — those live in
// ``backend/app/rules/default_pack.py`` and drive engine behaviour.
// Changing a UI band here re-tints the score cell; it does not affect
// any score value or any engine output.
//
// If a CA looks at a score of 65 and reads "amber," and next month
// a rule-pack update recomputes their score to 62, we want the tint
// to stay the same shape (still amber) so the visual language stays
// stable while the underlying number moves. That's the reason for
// the separation.
// ---------------------------------------------------------------------------


export type ScoreBand = "red" | "amber" | "green" | "null";


export function scoreBand(score: number | null): ScoreBand {
  if (score === null || score === undefined) return "null";
  if (score < 50) return "red";
  if (score < 80) return "amber";
  return "green";
}


export const scoreBandTint: Record<ScoreBand, { fg: string; bg: string; arc: string }> = {
  red:   { fg: palette.redFg,   bg: palette.redBg,   arc: palette.redStrong },
  amber: { fg: palette.amberFg, bg: palette.amberBg, arc: palette.amberStrong },
  green: { fg: palette.greenFg, bg: palette.greenBg, arc: palette.greenStrong },
  null:  { fg: palette.greyFg,  bg: "transparent",   arc: palette.greyFg },
};


// ---------------------------------------------------------------------------
// Reconciliation bucket → colour. Defined ONCE — every component
// that renders a bucket chip imports from here. Grep for local bucket
// colours is a review check.
// ---------------------------------------------------------------------------


export type BucketKey =
  | "matched"
  | "probable"
  | "supplier_default"
  | "missing_entry";


export const bucketTint: Record<BucketKey, { fg: string; bg: string }> = {
  matched:          { fg: palette.greenFg,  bg: palette.greenBg },
  probable:         { fg: palette.accent,   bg: palette.accentTint },
  supplier_default: { fg: palette.amberFg,  bg: palette.amberBg },
  missing_entry:    { fg: palette.greyFg,   bg: palette.greyBg },
};


// ---------------------------------------------------------------------------
// Days-to-due urgency tint (command center + workspace).
// ---------------------------------------------------------------------------


export function urgencyTint(days: number | null): { fg: string; bg: string } | null {
  if (days === null || days === undefined) return null;
  if (days <= 3) return { fg: palette.redFg, bg: palette.redBg };
  return null;
}
