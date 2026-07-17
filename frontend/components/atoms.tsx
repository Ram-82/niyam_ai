/**
 * Small display atoms shared across pages. Each one enforces one of
 * the step-9 acceptance criteria so a criterion regression can only
 * happen by editing this file.
 */
import Link from "next/link";
import { CDN_DISCLAIMER } from "@/lib/constants";
import { formatPaise } from "@/lib/format";
import type { Blocker } from "@/lib/types";


/**
 * Criterion #1: every ITC figure renders with the CDN disclaimer.
 * Use ``variant="tooltip"`` for column headers/cells (native title
 * attribute so it's screenreader-visible), ``variant="footnote"`` for
 * summary panels where a visible caption is warranted.
 */
export function ITCCell({
  paise,
  variant = "tooltip",
}: {
  paise: number;
  variant?: "tooltip" | "footnote";
}) {
  const formatted = formatPaise(paise);
  if (variant === "footnote") {
    return (
      <span className="font-mono">
        {formatted}
        <span className="ml-2 text-xs text-neutral-500">
          ({CDN_DISCLAIMER})
        </span>
      </span>
    );
  }
  return (
    <span className="font-mono" title={CDN_DISCLAIMER}>
      {formatted}
    </span>
  );
}


/**
 * Column header helper: adds an aria-friendly tooltip carrying the
 * CDN disclaimer. Wraps the label text; append " (ⓘ)" so users know
 * to hover.
 */
export function ITCHeader({ label }: { label: string }) {
  return (
    <span title={CDN_DISCLAIMER}>
      {label} <span className="text-neutral-400">ⓘ</span>
    </span>
  );
}


/**
 * Criterion #3: NULL score renders as "Not yet scored", never 0/blank.
 * Colour-coded when the score is present.
 */
export function ScoreCell({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <span className="text-neutral-500 italic" data-testid="not-yet-scored">
        Not yet scored
      </span>
    );
  }
  const colour =
    score >= 80 ? "text-green-700"
    : score >= 60 ? "text-amber-700"
    : "text-red-700";
  return (
    <span className={`font-mono font-semibold ${colour}`}>{score}</span>
  );
}


/**
 * Criterion #5: blockers render owner + paise_impact.
 */
export function BlockersList({ blockers }: { blockers: Blocker[] }) {
  if (blockers.length === 0) {
    return <p className="text-sm text-neutral-500">No blockers.</p>;
  }
  return (
    <ul className="divide-y divide-neutral-200 border border-neutral-200 rounded">
      {blockers.map((b) => (
        <li key={b.code} className="p-3 flex items-start gap-3">
          <OwnerBadge owner={b.owner} />
          <div className="flex-1">
            <div className="text-sm font-medium">{b.description}</div>
            <div className="text-xs text-neutral-500">{b.code}</div>
          </div>
          <div className="text-right">
            {b.paise_impact > 0 ? (
              <ITCCell paise={b.paise_impact} />
            ) : (
              <span className="text-xs text-neutral-400">—</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}


export function OwnerBadge({ owner }: { owner: "ca" | "client" }) {
  const label = owner === "ca" ? "CA" : "Client";
  const cls =
    owner === "ca"
      ? "bg-blue-100 text-blue-800"
      : "bg-purple-100 text-purple-800";
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${cls}`}>
      {label}
    </span>
  );
}


/**
 * Criterion #7: anything backed by a stub interface is visibly labelled
 * so a demo doesn't accidentally imply a feature works. Wrap the
 * feature in <StubBadge>Send report to client</StubBadge>.
 */
export function StubBadge({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs bg-yellow-100 text-yellow-900 px-2 py-0.5 rounded border border-yellow-300"
      title="This feature is stubbed. Wired up in P2."
    >
      <span aria-hidden>⚙</span>
      {children}
      <span className="uppercase tracking-wide text-[10px] opacity-70">
        stubbed
      </span>
    </span>
  );
}


/**
 * Criterion #4: score click opens the persisted arithmetic JSONB.
 * The panel is presentational only — it does no math, just renders
 * whatever the API returned.
 */
export function ArithmeticPanel({
  arithmetic,
}: {
  arithmetic: {
    components?: Array<{
      name: string;
      value: number;
      raw_weight: number;
      normalized_weight: number;
      weighted_contribution: number;
    }>;
    weighted_sum?: number;
    final_score?: number;
    rule_pack_version?: string;
    computed_for_date?: string;
    days_to_due_date?: number;
  };
}) {
  if (!arithmetic.components) {
    return (
      <div className="text-sm text-neutral-500 italic">
        No stored arithmetic — trigger a score to compute one.
      </div>
    );
  }
  return (
    <div className="text-sm">
      <p className="mb-2 text-neutral-600">
        Score computed under rule_pack{" "}
        <span className="font-mono">{arithmetic.rule_pack_version}</span>
        {arithmetic.computed_for_date && (
          <> on {arithmetic.computed_for_date}</>
        )}
        . Values below are the stored math, not a recomputation.
      </p>
      <table className="w-full text-xs border border-neutral-200">
        <thead className="bg-neutral-50">
          <tr>
            <th className="text-left p-2">Component</th>
            <th className="text-right p-2">Value</th>
            <th className="text-right p-2">Raw&nbsp;wt</th>
            <th className="text-right p-2">Norm&nbsp;wt</th>
            <th className="text-right p-2">Weighted</th>
          </tr>
        </thead>
        <tbody>
          {arithmetic.components.map((c) => (
            <tr key={c.name} className="border-t border-neutral-200">
              <td className="p-2 font-mono">{c.name}</td>
              <td className="p-2 text-right font-mono">{c.value.toFixed(2)}</td>
              <td className="p-2 text-right font-mono">{c.raw_weight}</td>
              <td className="p-2 text-right font-mono">
                {c.normalized_weight.toFixed(4)}
              </td>
              <td className="p-2 text-right font-mono">
                {c.weighted_contribution.toFixed(4)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="bg-neutral-50 font-semibold">
          <tr>
            <td className="p-2" colSpan={4}>
              Weighted sum → Final score
            </td>
            <td className="p-2 text-right font-mono">
              {arithmetic.weighted_sum?.toFixed(4)} → {arithmetic.final_score}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}


/**
 * Criterion #2: near_misses render as a review list. The chase action
 * IS the "confirm as match" button on each near-miss row — never a
 * one-click "chase supplier" button that skips this review.
 */
export function NearMissReview({
  nearMisses,
  onConfirm,
}: {
  nearMisses: NonNullable<
    import("@/lib/types").MatchResult["context"]["near_misses"]
  >;
  onConfirm?: (b2bEntryId: string) => void;
}) {
  // An ungated supplier_default row must never be a reachable state.
  // Both branches below explicitly frame "supplier default" as a
  // hypothesis, not a conclusion.
  if (nearMisses.length === 0) {
    return (
      <div
        className="text-sm p-3 bg-neutral-50 border border-neutral-200 rounded"
        data-testid="near-miss-empty"
      >
        <span className="font-medium">
          No same-supplier candidates found.
        </span>{" "}
        Verify register entry details (supplier GSTIN, invoice number,
        period) before assuming supplier default.
      </div>
    );
  }
  return (
    <div className="space-y-2" data-testid="near-miss-list">
      <p className="text-sm font-medium text-amber-900 bg-amber-50 border border-amber-200 rounded p-2">
        Review these possible matches from the same supplier BEFORE
        drafting a chase — the invoice may already be in the 2B under a
        slightly different number or amount.
      </p>
      <ul className="border border-neutral-200 rounded divide-y">
        {nearMisses.map((nm) => (
          <li key={nm.b2b_entry_id} className="p-3 text-sm">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-neutral-500">
                sim {nm.similarity.toFixed(2)}
              </span>
              <span className="font-mono">{nm.invoice_number}</span>
              <span className="text-neutral-500">{nm.invoice_date}</span>
              <span className="ml-auto">
                <ITCCell paise={nm.total_paise} />
              </span>
              {onConfirm && (
                <button
                  className="ml-3 px-2 py-1 text-xs bg-blue-600 text-white rounded"
                  onClick={() => onConfirm(nm.b2b_entry_id)}
                >
                  This is the match
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
