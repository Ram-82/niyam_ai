/**
 * Renders the four prose blocks the LLM narrator produces for the
 * client-facing 2-pager. The CA reviews the copy here BEFORE any
 * delivery request is created — nothing on this screen sends anything.
 *
 * Design rule (from feedback-review-gate + positioning): the CA is
 * the final human authority; the machine copy is presented as a draft,
 * not as finished output. The header, tone, and "regenerate" affordance
 * all reinforce that framing.
 */
"use client";

import type { NarrationOutput } from "@/lib/types";
import { NARRATION_LANGUAGE_LABELS } from "@/lib/constants";


export function NarrationPreview({
  narration,
  onRegenerate,
  regenerating,
}: {
  narration: NarrationOutput;
  onRegenerate?: () => void;
  regenerating?: boolean;
}) {
  return (
    <div
      className="bg-paper-raised border border-rule rounded-md p-4 space-y-4"
      data-testid="narration-preview"
    >
      <div className="flex items-baseline gap-3 flex-wrap">
        <h3 className="text-sm font-semibold text-ink">
          Draft 2-pager · {NARRATION_LANGUAGE_LABELS[narration.language] || narration.language}
        </h3>
        <span className="text-xs text-ink-muted font-mono">
          {narration.provider}/{narration.model}
        </span>
        {onRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={regenerating}
            className="ml-auto text-xs text-accent hover:text-accent-hover hover:underline font-semibold disabled:opacity-50"
            data-testid="regenerate-narration"
          >
            {regenerating ? "Regenerating…" : "Regenerate"}
          </button>
        )}
      </div>

      <div className="space-y-3 text-sm">
        <NarrationBlock heading="Business health" body={narration.page1_health} />
        <NarrationBlock heading="Tax position" body={narration.page1_tax_position} />
        <NarrationBlock heading="Needs attention" body={narration.page2_attention} />
        {narration.page2_ask_your_ca && (
          <NarrationBlock
            heading="Ask your CA"
            body={narration.page2_ask_your_ca}
          />
        )}
      </div>

      <p className="text-xs text-ink-muted italic">
        Every rupee figure above is verified against the deterministic
        engine outputs — the model cannot invent a number.
      </p>
    </div>
  );
}


function NarrationBlock({ heading, body }: { heading: string; body: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-ink-muted font-semibold mb-1">
        {heading}
      </div>
      <p className="text-ink whitespace-pre-line">{body}</p>
    </div>
  );
}
