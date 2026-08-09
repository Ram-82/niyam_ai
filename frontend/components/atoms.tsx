/**
 * Small display atoms shared across pages. Each one enforces one of
 * the load-bearing honesty features — restyled, never reworded.
 */
import { CDN_DISCLAIMER } from "@/lib/constants";
import { formatPaise } from "@/lib/format";
import { formatDateIN } from "@/lib/format-date";
import { ScoreBadge } from "@/components/ScoreBadge";
import type { Blocker } from "@/lib/types";


/**
 * Criterion #1 (from step 9) + stage-1 condition #1:
 * every ITC figure renders with the CDN disclaimer.
 *
 * ``variant="tooltip"`` — inline cell. Adds a dotted-underline
 * affordance under the money so hovering is discoverable and the
 * native title attribute carries the disclaimer text.
 * ``variant="footnote"`` — the disclaimer renders visibly beside the
 * value at --text-xs in --ink (never lightened grey), per condition #1.
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
      <span className="font-mono inline-flex items-baseline gap-2">
        {formatted}
        <span className="text-xs text-ink italic">
          ({CDN_DISCLAIMER})
        </span>
      </span>
    );
  }
  return (
    <span
      className="font-mono border-b border-dotted border-ink-muted cursor-help"
      title={CDN_DISCLAIMER}
    >
      {formatted}
    </span>
  );
}


/**
 * Column-header helper: dotted underline + ⓘ glyph so the CDN
 * disclaimer tooltip is discoverable. Never abbreviated away.
 */
export function ITCHeader({ label }: { label: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 border-b border-dotted border-ink-muted cursor-help"
      title={CDN_DISCLAIMER}
    >
      {label}
      <span aria-hidden="true" className="text-ink-muted">ⓘ</span>
    </span>
  );
}


/**
 * NULL score renders as "Not yet scored", never 0/blank. Delegates
 * to ScoreBadge — the single visual treatment for score everywhere.
 */
export function ScoreCell({
  score,
  size = "sm",
}: {
  score: number | null;
  size?: "sm" | "md" | "lg";
}) {
  return <ScoreBadge score={score} size={size} />;
}


/**
 * Blockers render owner + paise_impact — the sort key of the
 * command center. Restyled, semantics + testids untouched.
 */
export function BlockersList({ blockers }: { blockers: Blocker[] }) {
  if (blockers.length === 0) {
    return <p className="text-sm text-ink-muted">No blockers.</p>;
  }
  return (
    <ul className="divide-y divide-rule border border-rule rounded-md bg-paper-raised">
      {blockers.map((b) => (
        <li key={b.code} className="p-3 flex items-start gap-3">
          <OwnerBadge owner={b.owner} />
          <div className="flex-1 min-w-0">
            <div className="text-sm text-ink">{b.description}</div>
            <div className="text-xs text-ink-muted font-mono mt-0.5">{b.code}</div>
          </div>
          <div className="text-right whitespace-nowrap">
            {b.paise_impact > 0 ? (
              <ITCCell paise={b.paise_impact} />
            ) : (
              <span className="text-xs text-ink-muted">—</span>
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
      ? "bg-accent-tint text-accent"
      : "bg-grey-bg text-ink";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-sm ${cls}`}>
      {label}
    </span>
  );
}


const FILING_STATUS_GLYPH: Record<string, { glyph: string; label: string; cls: string }> = {
  draft:    { glyph: "◑", label: "Draft",    cls: "bg-amber-bg text-amber-fg" },
  approved: { glyph: "◆", label: "Approved", cls: "bg-stamp-tint text-stamp" },
  filed:    { glyph: "●", label: "Filed",    cls: "bg-green-bg text-green-fg" },
};

/**
 * Filing-status chip with a glyph in a fixed 9px slot so the state
 * reads in greyscale and survives colour-blindness.
 */
export function StateChip({ status }: { status: string | null | undefined }) {
  if (!status) {
    return <span className="text-xs text-ink-muted">Not started</span>;
  }
  const s = FILING_STATUS_GLYPH[status];
  if (!s) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-sm bg-grey-bg text-ink-muted">
        {status}
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-sm ${s.cls}`}>
      <span className="inline-block w-[9px] text-center shrink-0" aria-hidden="true">{s.glyph}</span>
      {s.label}
    </span>
  );
}


/**
 * Anything backed by a stub interface must be visibly labelled so a
 * demo can't accidentally imply a feature works.
 */
export function StubBadge({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs bg-amber-bg text-amber-fg px-2 py-0.5 rounded-sm border border-rule"
      title="This feature is stubbed. Wired up in P2."
    >
      <span aria-hidden="true">⚙</span>
      {children}
      <span className="uppercase tracking-wide text-[10px] opacity-80">
        stubbed
      </span>
    </span>
  );
}


/**
 * Score click opens the persisted arithmetic JSONB — presentational
 * only, no math. Rule pack version + computed_for_date are shown so
 * the reader knows exactly which snapshot they're staring at.
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
      <div className="text-sm text-ink-muted italic">
        No stored arithmetic — trigger a score to compute one.
      </div>
    );
  }
  return (
    <div className="text-sm">
      <p className="mb-3 text-ink-muted">
        Score computed under rule_pack{" "}
        <span className="font-mono text-ink">{arithmetic.rule_pack_version}</span>
        {arithmetic.computed_for_date && (
          <> on <span className="font-mono text-ink">{arithmetic.computed_for_date}</span></>
        )}
        . Values below are the stored math, not a recomputation.
      </p>
      <table className="w-full text-xs border border-rule rounded-md overflow-hidden">
        <thead className="bg-paper text-ink-muted uppercase tracking-wide">
          <tr>
            <th className="text-left p-2">Component</th>
            <th className="text-right p-2">Value</th>
            <th className="text-right p-2">Raw wt</th>
            <th className="text-right p-2">Norm wt</th>
            <th className="text-right p-2">Weighted</th>
          </tr>
        </thead>
        <tbody>
          {arithmetic.components.map((c) => (
            <tr key={c.name} className="border-t border-rule">
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
        <tfoot className="bg-paper font-semibold">
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
 * NearMissReview — both empty and populated states render (an
 * ungated supplier_default row is never a reachable state). Copy is
 * verbatim from the step-9 acceptance criteria — restyled only.
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
  if (nearMisses.length === 0) {
    return (
      <div
        className="text-sm p-3 bg-paper border border-rule rounded-md text-ink"
        data-testid="near-miss-empty"
      >
        <span className="font-semibold">
          No same-supplier candidates found.
        </span>{" "}
        Verify register entry details (supplier GSTIN, invoice number,
        period) before assuming supplier default.
      </div>
    );
  }
  return (
    <div className="space-y-2" data-testid="near-miss-list">
      <p className="text-sm font-semibold text-amber-fg bg-amber-bg border border-rule rounded-md p-2">
        Review these possible matches from the same supplier BEFORE
        drafting a chase — the invoice may already be in the 2B under a
        slightly different number or amount.
      </p>
      <ul className="border border-rule rounded-md divide-y divide-rule bg-paper-raised">
        {nearMisses.map((nm) => (
          <li key={nm.b2b_entry_id} className="p-3 text-sm">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="font-mono text-xs text-ink-muted">
                sim {nm.similarity.toFixed(2)}
              </span>
              <span className="font-mono">{nm.invoice_number}</span>
              <span className="text-ink-muted font-mono">{formatDateIN(nm.invoice_date)}</span>
              <span className="ml-auto">
                <ITCCell paise={nm.total_paise} />
              </span>
              {onConfirm && (
                <button
                  className="px-2 py-1 text-xs bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast"
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
