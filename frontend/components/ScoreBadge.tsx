/**
 * ScoreBadge — the signature.
 *
 * Everywhere a readiness score is displayed (command center cell,
 * workspace returns tab, arithmetic panel header), it uses THIS
 * component. Identical treatment across the product so the score
 * reads instantly from anywhere.
 *
 * NULL score renders as "Not yet scored" grey-italic — never 0, never
 * blank. That's a load-bearing honesty feature.
 */
import { scoreBand, scoreBandTint } from "@/lib/design-tokens";


type Size = "sm" | "md" | "lg";

const SIZES: Record<Size, { pill: string; num: string; arcW: number; arcH: number; strokeW: number }> = {
  // Table cell — 68x40, digit at text-lg
  sm: { pill: "px-2 py-1 min-w-[3.75rem]", num: "text-lg leading-none",   arcW: 44, arcH: 6,  strokeW: 2 },
  // Card header — 100x64
  md: { pill: "px-3 py-2 min-w-[5rem]",    num: "text-xl leading-none",   arcW: 64, arcH: 8,  strokeW: 2 },
  // Returns-tab hero
  lg: { pill: "px-4 py-3 min-w-[7rem]",    num: "text-score leading-none", arcW: 96, arcH: 10, strokeW: 3 },
};


export function ScoreBadge({
  score,
  size = "sm",
  testId,
}: {
  score: number | null;
  size?: Size;
  testId?: string;
}) {
  const band = scoreBand(score);
  const sz = SIZES[size];

  if (band === "null") {
    return (
      <span
        className="italic text-grey-fg text-sm"
        data-testid={testId ?? "not-yet-scored"}
      >
        Not yet scored
      </span>
    );
  }

  const tint = scoreBandTint[band];
  const clamped = Math.max(0, Math.min(100, score ?? 0));
  const pctW = (sz.arcW - sz.strokeW) * (clamped / 100);

  return (
    <span
      className={
        "inline-flex flex-col items-center rounded-md border border-rule font-mono " +
        sz.pill
      }
      style={{ background: tint.bg }}
      data-testid={testId ?? "score-badge"}
      title={`Readiness score ${clamped}/100`}
    >
      <span
        className={"font-semibold text-ink " + sz.num}
        style={{ color: "var(--ink)" }}
      >
        {clamped}
      </span>
      <svg
        width={sz.arcW}
        height={sz.arcH}
        role="presentation"
        aria-hidden="true"
        className="mt-1"
      >
        {/* Track */}
        <rect
          x={sz.strokeW / 2}
          y={sz.arcH / 2 - sz.strokeW / 2}
          width={sz.arcW - sz.strokeW}
          height={sz.strokeW}
          fill="var(--rule)"
          rx={sz.strokeW / 2}
        />
        {/* Fill */}
        <rect
          x={sz.strokeW / 2}
          y={sz.arcH / 2 - sz.strokeW / 2}
          width={pctW}
          height={sz.strokeW}
          fill={tint.arc}
          rx={sz.strokeW / 2}
        />
      </svg>
    </span>
  );
}
