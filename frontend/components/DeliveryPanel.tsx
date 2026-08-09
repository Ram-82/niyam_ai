/**
 * Delivery panel — the CA workflow for turning a readiness snapshot
 * into a WhatsApp 2-pager to the client.
 *
 * State machine (kept in one component so the transitions are
 * inspectable in one place):
 *
 *   idle                       — ready, no narration in-hand yet
 *                                → "Generate 2-pager"
 *   narration_ready            — draft in-hand → preview + "Send" CTA
 *   preparing                  — modal open, phone + language capture,
 *                                approve + send fires from Submit
 *   disabled                   — WHATSAPP_ENABLED=false on the backend
 *                                (detected on the first /whatsapp/attempts
 *                                call — 503 flips the panel)
 *
 * Narration is regenerated on-demand each session; we deliberately do
 * NOT persist "the current draft" across page loads. Rationale: numbers
 * change between sessions (fresh imports, new scoring runs), and a
 * stale draft displayed as current would violate the honesty contract
 * that the narrator module enforces at the paise level.
 *
 * The panel deliberately COLLAPSES the three backend steps
 * (create delivery_request → approve → send) into a single CA click
 * from the preparation modal. That is a UX-only optimisation — the
 * backend still writes the same three-step audit trail (delivery.
 * approved + report.sent), and the CA-approval gate is still enforced:
 * this UI cannot "send without approving" because the same handler
 * that submits the modal is the one that calls approve() before
 * send(). If a future flow needs to split those (e.g. reviewer vs
 * sender roles), separate the CTAs — but until then, fewer clicks.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, apiBlob, ApiError } from "@/lib/api";
import { NarrationPreview } from "@/components/NarrationPreview";
import { DeliveryAttemptsList } from "@/components/DeliveryAttemptsList";
import { NARRATION_LANGUAGE_LABELS } from "@/lib/constants";
import type {
  DeliveryAttemptRow,
  DeliveryRequestCreatedResponse,
  DeliverySendResponse,
  NarrationLanguage,
  NarrationOutput,
} from "@/lib/types";


/**
 * Panel state. Narration is generated on-demand each CA session so
 * the prose always matches the CURRENT readiness snapshot; we do not
 * preload a stored narration from a prior day (that risks sending
 * stale numbers). Every generation writes a fresh narration_run row
 * for audit.
 */
type Panel =
  | { state: "idle" }                                    // ready to generate
  | { state: "narrator_disabled" }                       // NARRATOR_ENABLED=false
  | { state: "whatsapp_disabled"; narration?: NarrationOutput }  // WHATSAPP_ENABLED=false
  | { state: "narration_ready"; narration: NarrationOutput }
  | { state: "preparing"; narration: NarrationOutput };


export function DeliveryPanel({
  gstinProfileId,
  period,
  returnType,
  clientId,
  clientWhatsappNumber,
  clientDefaultLanguage,
}: {
  gstinProfileId: string;
  period: string;
  returnType: "GSTR1" | "GSTR3B";
  /** Optional — enables the "save number to client" toggle in the modal. */
  clientId?: string;
  /** Prefill for the phone number field. */
  clientWhatsappNumber?: string;
  /** Prefill for the language field (defaults to en if omitted). */
  clientDefaultLanguage?: NarrationLanguage;
}) {
  const [panel, setPanel] = useState<Panel>({ state: "idle" });
  const [attempts, setAttempts] = useState<DeliveryAttemptRow[]>([]);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAttempts = useCallback(async () => {
    try {
      const rows = await api<DeliveryAttemptRow[]>(`/whatsapp/attempts?limit=25`);
      setAttempts(rows);
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        // WhatsApp disabled — still allow narration generation.
        setPanel((p) =>
          p.state === "narration_ready" || p.state === "preparing"
            ? { state: "whatsapp_disabled", narration: p.narration }
            : p.state === "idle" || p.state === "narrator_disabled"
            ? { state: "whatsapp_disabled" }
            : p
        );
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    loadAttempts();
  }, [loadAttempts]);

  async function generate(language: NarrationLanguage = "en") {
    setError(null);
    setRegenerating(true);
    try {
      const out = await api<NarrationOutput>("/narrator/preview", {
        method: "POST",
        body: {
          gstin_profile_id: gstinProfileId,
          period,
          return_type: returnType,
          language,
        },
      });
      setPanel({ state: "narration_ready", narration: out });
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        const detail = (e as ApiError).message ?? "";
        if (detail.includes("narrator_disabled")) {
          setPanel({ state: "narrator_disabled" });
        } else {
          // WhatsApp disabled mid-session.
          setPanel((p) =>
            p.state === "narration_ready" || p.state === "preparing"
              ? { state: "whatsapp_disabled", narration: p.narration }
              : { state: "whatsapp_disabled" }
          );
        }
        return;
      }
      if (e instanceof ApiError && e.status === 409) {
        setError(
          "No readiness snapshot yet for this period + return type. Run scoring on the Returns tab first.",
        );
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRegenerating(false);
    }
  }

  async function openPrepare() {
    if (panel.state !== "narration_ready") return;
    setPanel({ state: "preparing", narration: panel.narration });
  }

  async function previewPdf(narrationRunId: string) {
    setError(null);
    try {
      const blob = await apiBlob(`/narrator/runs/${narrationRunId}/pdf`);
      const url = URL.createObjectURL(blob);
      // Open in a new tab. Don't revoke the URL immediately — the tab
      // needs it to load the PDF. Browsers reclaim it on tab close.
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`PDF preview failed: ${e.message} (HTTP ${e.status})`);
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function submitSend(payload: {
    whatsappNumber: string;
    language: NarrationLanguage;
    templateName?: string;
    saveToClient: boolean;
  }) {
    if (panel.state !== "preparing") return;
    setError(null);
    try {
      // 0. (optional) Persist the number on the client record so next
      //    session prefills without CA input. Runs before the send so
      //    a send failure still leaves the client record updated.
      if (payload.saveToClient && clientId) {
        try {
          await api(`/clients/${clientId}`, {
            method: "PATCH",
            body: { whatsapp_number: payload.whatsappNumber },
          });
        } catch (e) {
          // Non-fatal: surface via error strip but proceed with send.
          setError(
            `Saving to client record failed: ${
              e instanceof Error ? e.message : String(e)
            }. Proceeding with send.`,
          );
        }
      }
      // 1. Create request.
      const created = await api<DeliveryRequestCreatedResponse>(
        "/whatsapp/delivery-requests",
        {
          method: "POST",
          body: {
            narration_run_id: panel.narration.narration_run_id,
            whatsapp_number: payload.whatsappNumber,
            language: payload.language,
            template_name: payload.templateName,
          },
        },
      );
      const reqId = created.delivery_request_id;
      // 2. Approve.
      await api(`/whatsapp/delivery-requests/${reqId}/approve`, {
        method: "POST",
      });
      // 3. Send — the backend auto-renders the PDF from the narration_run.
      const sent = await api<DeliverySendResponse>(
        `/whatsapp/delivery-requests/${reqId}/send`,
        { method: "POST", body: {} },
      );
      setPanel({ state: "narration_ready", narration: panel.narration });
      // Refresh attempts so the new row surfaces immediately.
      await loadAttempts();
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`Send failed: ${e.message} (HTTP ${e.status})`);
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }

  return (
    <div className="space-y-3" data-testid="delivery-panel">
      <h2 className="text-sm font-semibold text-ink">Client 2-pager delivery</h2>

      {error && (
        <p className="text-sm bg-red-bg border border-rule text-red-fg rounded-md px-3 py-2">
          {error}
        </p>
      )}

      {panel.state === "narrator_disabled" && <NarratorDisabledCallout />}

      {panel.state === "whatsapp_disabled" && <WhatsAppDisabledCallout />}

      {(panel.state === "idle" ||
        (panel.state === "whatsapp_disabled" && !panel.narration)) && (
        <NoNarrationCallout onGenerate={generate} generating={regenerating} />
      )}

      {(panel.state === "narration_ready" ||
        (panel.state === "whatsapp_disabled" && panel.narration)) && (
        <>
          <NarrationPreview
            narration={
              panel.state === "whatsapp_disabled" ? panel.narration! : panel.narration
            }
            onRegenerate={() =>
              generate(
                panel.state === "whatsapp_disabled"
                  ? panel.narration!.language
                  : panel.narration.language,
              )
            }
            regenerating={regenerating}
          />
          <div className="flex gap-3 flex-wrap">
            <button
              onClick={openPrepare}
              disabled={panel.state === "whatsapp_disabled"}
              className="px-4 py-2 bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast disabled:opacity-40 disabled:cursor-not-allowed"
              data-testid="prepare-delivery"
              title={panel.state === "whatsapp_disabled" ? "WhatsApp delivery is disabled" : undefined}
            >
              Send via WhatsApp
            </button>
            <button
              onClick={() => previewPdf(panel.narration.narration_run_id)}
              className="px-4 py-2 border border-rule bg-paper text-ink rounded-sm hover:border-rule-strong transition-colors duration-fast"
              data-testid="preview-pdf"
            >
              Preview PDF
            </button>
          </div>
        </>
      )}

      {panel.state === "preparing" && (
        <PrepareModal
          narration={panel.narration}

          defaultNumber={clientWhatsappNumber || ""}
          defaultLanguage={clientDefaultLanguage || panel.narration.language}
          allowSaveToClient={!!clientId}
          onCancel={() =>
            setPanel({ state: "narration_ready", narration: panel.narration })
          }
          onSubmit={submitSend}
        />
      )}

      <div>
        <h3 className="text-xs uppercase tracking-wide text-ink-muted font-semibold mb-2">
          Recent delivery attempts
        </h3>
        <DeliveryAttemptsList attempts={attempts} />
      </div>
    </div>
  );
}


function NarratorDisabledCallout() {
  return (
    <div className="text-sm p-3 bg-amber-bg border border-rule rounded-md text-amber-fg">
      <span className="font-semibold">Narration is disabled in this environment.</span>{" "}
      An admin needs to set <span className="font-mono">NARRATOR_ENABLED=true</span>{" "}
      (and optionally <span className="font-mono">NARRATOR_MODE=mock</span> to use the
      template engine without an API key).
    </div>
  );
}


function WhatsAppDisabledCallout() {
  return (
    <div className="text-sm p-3 bg-amber-bg border border-rule rounded-md text-amber-fg">
      <span className="font-semibold">WhatsApp delivery is disabled in this environment.</span>{" "}
      An admin needs to set <span className="font-mono">WHATSAPP_ENABLED=true</span>{" "}
      after the WABA sender is provisioned. Narration generation still works —
      you can review and download the PDF draft without sending.
    </div>
  );
}


function NoNarrationCallout({
  onGenerate,
  generating,
}: {
  onGenerate: (lang?: NarrationLanguage) => void;
  generating: boolean;
}) {
  return (
    <div className="bg-paper-raised border border-rule rounded-md p-4 space-y-3">
      <p className="text-sm text-ink">
        No 2-pager draft yet for this period. Generate one from the current
        readiness snapshot — the CA reviews and approves before anything is sent.
      </p>
      <button
        onClick={() => onGenerate("en")}
        disabled={generating}
        className="px-4 py-2 bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
        data-testid="generate-narration"
      >
        {generating ? "Generating…" : "Generate 2-pager"}
      </button>
    </div>
  );
}


function PrepareModal({
  narration,
  defaultNumber,
  defaultLanguage,
  allowSaveToClient,
  onCancel,
  onSubmit,
}: {
  narration: NarrationOutput;
  defaultNumber: string;
  defaultLanguage: NarrationLanguage;
  allowSaveToClient: boolean;
  onCancel: () => void;
  onSubmit: (payload: {
    whatsappNumber: string;
    language: NarrationLanguage;
    templateName?: string;
    saveToClient: boolean;
  }) => void;
}) {
  const [number, setNumber] = useState(defaultNumber);
  const [language, setLanguage] = useState<NarrationLanguage>(defaultLanguage);
  // Default: opt-in to save when we didn't have a stored number (or
  // the CA changed the prefilled one). Opt-out when the number was
  // prefilled and unchanged.
  const [saveToClient, setSaveToClient] = useState(defaultNumber === "");
  const [submitting, setSubmitting] = useState(false);

  const validE164 = /^\+[1-9]\d{7,14}$/.test(number.trim());
  const numberChanged = number.trim() !== defaultNumber;

  return (
    <div
      className="bg-paper-raised border border-accent rounded-md p-4 space-y-3"
      data-testid="prepare-modal"
    >
      <h3 className="text-sm font-semibold text-ink">Prepare delivery</h3>
      <p className="text-xs text-ink-muted">
        Once you click Approve & Send, Niyam records CA approval, sends the
        WhatsApp template message, and locks this delivery request. To send
        again, generate a fresh draft.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            WhatsApp number (E.164)
          </span>
          <input
            type="text"
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            placeholder="+91XXXXXXXXXX"
            className="mt-1 w-full border border-rule rounded-sm px-2 py-1 text-sm font-mono bg-paper"
            data-testid="whatsapp-number"
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
            data-testid="whatsapp-language"
          >
            {Object.entries(NARRATION_LANGUAGE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          {language !== narration.language && (
            <span className="text-xs text-amber-fg mt-1 block">
              Note: the draft above was in {NARRATION_LANGUAGE_LABELS[narration.language]}.
              Send will use the template for {NARRATION_LANGUAGE_LABELS[language]};
              regenerate the draft in the same language first for a truthful send.
            </span>
          )}
        </label>
      </div>

      {allowSaveToClient && (
        <label className="flex items-start gap-2 text-xs text-ink">
          <input
            type="checkbox"
            checked={saveToClient}
            onChange={(e) => setSaveToClient(e.target.checked)}
            className="mt-0.5"
            data-testid="save-to-client"
          />
          <span>
            {defaultNumber
              ? numberChanged
                ? "Update the client's stored WhatsApp number so next send prefills the new number."
                : "Overwrite the stored client number (unchanged — usually leave this off)."
              : "Save this WhatsApp number to the client record so the next send prefills it."}
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
                saveToClient: allowSaveToClient && saveToClient,
              });
            } finally {
              setSubmitting(false);
            }
          }}
          disabled={!validE164 || submitting}
          className="px-4 py-2 bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50"
          data-testid="approve-and-send"
        >
          {submitting ? "Sending…" : "Approve & Send"}
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
