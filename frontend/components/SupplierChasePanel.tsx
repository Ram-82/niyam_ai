/**
 * Supplier-chase workflow — the per-row action set on a supplier_default
 * match_result. Owns three CTAs:
 *
 *   1. NearMissReview list (from atoms) — always visible.
 *   2. "Mark near-misses reviewed" — enabled iff the CA has not
 *      already done it. Calls POST /match-results/{id}/mark-near-miss-
 *      reviewed. Sets match_result.context.near_miss_reviewed_at.
 *   3. "Send chase to supplier" — enabled ONLY after #2. Opens a modal
 *      that captures the supplier's WhatsApp E.164 + language and does
 *      the create → approve → send handshake against /whatsapp/*.
 *
 * The disable rule on #3 mirrors the backend gate exactly
 * (app/whatsapp/gate.py: near_miss_reviewed_at required for chases).
 * If the two ever drift, the backend refuses the send with a
 * NearMissReviewMissing → 409; the panel surfaces that as an error,
 * not a crash.
 *
 * Design decision on scope — the supplier's phone number is NOT stored
 * anywhere yet (no supplier contact table). The CA types it into the
 * modal each time. When a supplier_contact table lands, prefill it
 * from there.
 */
"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { NearMissReview } from "@/components/atoms";
import { DeliveryAttemptsList } from "@/components/DeliveryAttemptsList";
import { NARRATION_LANGUAGE_LABELS } from "@/lib/constants";
import { formatTimestampIN } from "@/lib/format-date";
import type {
  DeliveryAttemptRow,
  DeliveryRequestCreatedResponse,
  DeliverySendResponse,
  MatchResult,
  NarrationLanguage,
  SupplierContactRow,
} from "@/lib/types";


type State =
  | { kind: "idle" }              // not reviewed yet
  | { kind: "reviewing" }         // POST in flight
  | { kind: "reviewed" }          // ready to chase
  | { kind: "preparing" }         // chase modal open
  | { kind: "disabled" };         // whatsapp feature flag off


export function SupplierChasePanel({
  match,
  onLocalUpdate,
}: {
  match: MatchResult;
  /** Called after a successful mark-reviewed so the parent can update
   * its local list without a full refetch. Optional. */
  onLocalUpdate?: (patch: Partial<MatchResult["context"]>) => void;
}) {
  const reviewedAt = match.context.near_miss_reviewed_at;
  const [state, setState] = useState<State>(
    reviewedAt ? { kind: "reviewed" } : { kind: "idle" },
  );
  const [attempts, setAttempts] = useState<DeliveryAttemptRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function markReviewed() {
    setError(null);
    setState({ kind: "reviewing" });
    try {
      const body = await api<{ id: string; near_miss_reviewed_at: string }>(
        `/match-results/${match.id}/mark-near-miss-reviewed`,
        { method: "POST" },
      );
      onLocalUpdate?.({ near_miss_reviewed_at: body.near_miss_reviewed_at });
      setState({ kind: "reviewed" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState({ kind: "idle" });
    }
  }

  const [prefill, setPrefill] = useState<SupplierContactRow | null>(null);

  async function openChase() {
    setError(null);
    // Peek /whatsapp/attempts once so we can flip to disabled if the
    // feature flag is off — better than opening a modal that will 503.
    try {
      const rows = await api<DeliveryAttemptRow[]>(
        `/whatsapp/attempts?limit=25`,
      );
      setAttempts(rows);
      // Try the supplier-contacts prefill lookup by GSTIN. A 404 is
      // expected for a supplier not yet in the directory; treat as
      // "no prefill" (silent). Any other error is a real failure worth
      // showing — but we still open the modal so the CA can proceed.
      const gstin = match.context.supplier_gstin;
      if (gstin) {
        try {
          const contact = await api<SupplierContactRow>(
            `/supplier-contacts/by-gstin/${gstin}`,
          );
          setPrefill(contact);
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) {
            setPrefill(null);
          } else {
            // Log via the error strip but let the modal open — the CA
            // can still send by typing the number.
            setError(
              `Supplier directory lookup failed: ${
                e instanceof Error ? e.message : String(e)
              }`,
            );
          }
        }
      } else {
        setPrefill(null);
      }
      setState({ kind: "preparing" });
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setState({ kind: "disabled" });
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function submitChase(payload: {
    whatsappNumber: string;
    language: NarrationLanguage;
    saveToDirectory: boolean;
    directoryName: string;
  }) {
    setError(null);
    try {
      // If the CA opted to save + we don't already have a contact for
      // this supplier, insert/update the directory row FIRST — that way
      // even if the send fails downstream, the directory entry is on
      // record and prefills next time. 409 (already exists) is fine —
      // it means the CA is chasing a supplier already in the directory.
      const gstin = match.context.supplier_gstin;
      if (payload.saveToDirectory && gstin) {
        try {
          const saved = await api<SupplierContactRow>("/supplier-contacts", {
            method: "POST",
            body: {
              supplier_gstin: gstin,
              name: payload.directoryName || gstin,
              whatsapp_number: payload.whatsappNumber,
            },
          });
          setPrefill(saved);
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            // Already in directory — PATCH the number in case it changed.
            if (prefill) {
              await api(`/supplier-contacts/${prefill.id}`, {
                method: "PATCH",
                body: { whatsapp_number: payload.whatsappNumber },
              });
            }
          } else {
            // Non-fatal: log via error strip but still proceed with the
            // chase send (the directory-save is a convenience, not a
            // precondition).
            setError(
              `Saving to directory failed: ${
                e instanceof Error ? e.message : String(e)
              }. Proceeding with chase send.`,
            );
          }
        }
      }

      const created = await api<DeliveryRequestCreatedResponse>(
        "/whatsapp/delivery-requests/chase",
        {
          method: "POST",
          body: {
            match_result_id: match.id,
            whatsapp_number: payload.whatsappNumber,
            language: payload.language,
          },
        },
      );
      const reqId = created.delivery_request_id;
      await api(`/whatsapp/delivery-requests/${reqId}/approve`, {
        method: "POST",
      });
      const sent = await api<DeliverySendResponse>(
        `/whatsapp/delivery-requests/${reqId}/send`,
        { method: "POST", body: {} },
      );
      onLocalUpdate?.({ last_chase_delivery_request_id: reqId });
      // Refresh attempts list so the fresh row surfaces.
      const rows = await api<DeliveryAttemptRow[]>(
        `/whatsapp/attempts?limit=25`,
      );
      setAttempts(rows);
      setState({ kind: "reviewed" });
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 409 && e.message === "near_miss_review_missing") {
          setError(
            "Backend rejected the chase: near-miss review is missing. Mark reviewed again and retry.",
          );
          setState({ kind: "idle" });
          return;
        }
        setError(`${e.message} (HTTP ${e.status})`);
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  return (
    <div className="space-y-3" data-testid={`chase-panel-${match.id}`}>
      <NearMissReview nearMisses={match.context.near_misses || []} />

      {error && (
        <p className="text-sm bg-red-bg border border-rule text-red-fg rounded-md px-3 py-2">
          {error}
        </p>
      )}

      {state.kind === "disabled" && (
        <div className="text-xs p-2 bg-amber-bg border border-rule rounded-md text-amber-fg">
          WhatsApp delivery is disabled in this environment — the chase
          message can be drafted but not sent.
        </div>
      )}

      <div className="flex gap-2 flex-wrap items-center">
        {!reviewedAt && state.kind !== "reviewed" && (
          <button
            onClick={markReviewed}
            disabled={state.kind === "reviewing"}
            className="px-3 py-1 text-xs bg-paper border border-rule text-ink font-semibold rounded-sm hover:border-rule-strong transition-colors duration-fast disabled:opacity-50"
            data-testid="mark-near-miss-reviewed"
          >
            {state.kind === "reviewing" ? "Marking…" : "Mark near-misses reviewed"}
          </button>
        )}

        {(reviewedAt || state.kind === "reviewed") && (
          <>
            <span className="text-xs text-ink-muted italic">
              Reviewed{" "}
              <span className="font-mono">
                {formatTimestampIN(
                  match.context.near_miss_reviewed_at || new Date().toISOString(),
                )}
              </span>
            </span>
            {state.kind !== "disabled" && (
              <button
                onClick={openChase}
                className="px-3 py-1 text-xs bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast"
                data-testid="send-chase"
              >
                Send chase to supplier
              </button>
            )}
          </>
        )}
      </div>

      {state.kind === "preparing" && (
        <ChaseModal
          match={match}
          prefill={prefill}
          onCancel={() => setState({ kind: "reviewed" })}
          onSubmit={submitChase}
        />
      )}

      {attempts && attempts.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-muted font-semibold mb-1">
            Recent chase attempts (firm-wide)
          </div>
          <DeliveryAttemptsList attempts={attempts.slice(0, 5)} />
        </div>
      )}
    </div>
  );
}


function ChaseModal({
  match,
  prefill,
  onCancel,
  onSubmit,
}: {
  match: MatchResult;
  prefill: SupplierContactRow | null;
  onCancel: () => void;
  onSubmit: (payload: {
    whatsappNumber: string;
    language: NarrationLanguage;
    saveToDirectory: boolean;
    directoryName: string;
  }) => void;
}) {
  const [number, setNumber] = useState(prefill?.whatsapp_number ?? "");
  const [language, setLanguage] = useState<NarrationLanguage>("en");
  // Default: opt-in to save when this is a NEW supplier (no prefill),
  // opt-out when we already had a directory entry (the CA presumably
  // just wants to send with the on-file number).
  const [saveToDirectory, setSaveToDirectory] = useState(prefill === null);
  const [directoryName, setDirectoryName] = useState(prefill?.name ?? "");
  const [submitting, setSubmitting] = useState(false);

  const validE164 = /^\+[1-9]\d{7,14}$/.test(number.trim());
  const supplierGstin = match.context.supplier_gstin;

  return (
    <div
      className="bg-paper-raised border border-accent rounded-md p-4 space-y-3"
      data-testid="chase-modal"
    >
      <h3 className="text-sm font-semibold text-ink">Send supplier chase</h3>
      <p className="text-xs text-ink-muted">
        This sends the approved chase template to the supplier's WhatsApp.
        Uses the sender WABA registered against your firm — the client sees
        the message coming from your firm's brand, not from Niyam.
      </p>

      {supplierGstin && (
        <div className="text-xs bg-paper border border-rule rounded-sm p-2">
          <span className="text-ink-muted">Supplier GSTIN:</span>{" "}
          <span className="font-mono text-ink">{supplierGstin}</span>
          {prefill && (
            <span className="ml-2 text-green-fg font-semibold">
              · prefilled from directory ({prefill.name})
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            Supplier WhatsApp (E.164)
          </span>
          <input
            type="text"
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            placeholder="+91XXXXXXXXXX"
            className="mt-1 w-full border border-rule rounded-sm px-2 py-1 text-sm font-mono bg-paper"
            data-testid="chase-whatsapp-number"
          />
          {number && !validE164 && (
            <span className="text-xs text-red-fg mt-1 block">
              Must be an E.164 number (+ followed by 8–15 digits).
            </span>
          )}
        </label>

        <label className="block text-sm">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            Language
          </span>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as NarrationLanguage)}
            className="mt-1 w-full border border-rule rounded-sm px-2 py-1 text-sm bg-paper"
            data-testid="chase-language"
          >
            {Object.entries(NARRATION_LANGUAGE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>

      {supplierGstin && (
        <label className="flex items-start gap-2 text-xs text-ink">
          <input
            type="checkbox"
            checked={saveToDirectory}
            onChange={(e) => setSaveToDirectory(e.target.checked)}
            className="mt-0.5"
            data-testid="save-to-directory"
          />
          <span>
            {prefill
              ? "Update this supplier in your directory if the number changed."
              : "Save this supplier to your firm's directory so the next chase prefills."}
            {saveToDirectory && !prefill && (
              <span className="block mt-1">
                <input
                  type="text"
                  value={directoryName}
                  onChange={(e) => setDirectoryName(e.target.value)}
                  placeholder="Supplier name (e.g. Ravi Textiles)"
                  className="border border-rule rounded-sm px-2 py-1 text-sm bg-paper w-full max-w-sm"
                  data-testid="directory-name"
                />
              </span>
            )}
          </span>
        </label>
      )}

      <div className="flex gap-3">
        <button
          onClick={async () => {
            setSubmitting(true);
            try {
              await onSubmit({
                whatsappNumber: number.trim(),
                language,
                saveToDirectory: !!supplierGstin && saveToDirectory,
                directoryName: directoryName.trim(),
              });
            } finally {
              setSubmitting(false);
            }
          }}
          disabled={
            !validE164
            || submitting
            || (saveToDirectory && !prefill && !directoryName.trim())
          }
          className="px-4 py-2 bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
          data-testid="approve-and-send-chase"
        >
          {submitting ? "Sending…" : "Approve & Send chase"}
        </button>
        <button
          onClick={onCancel}
          disabled={submitting}
          className="px-4 py-2 border border-rule bg-paper text-ink rounded-sm hover:border-rule-strong disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
