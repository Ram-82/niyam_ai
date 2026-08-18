"use client";
/**
 * OCR panel — upload an invoice PDF/photo, review the draft extraction,
 * accept (materialises an Invoice row) or reject.
 *
 * Panel states:
 *  - loading     — fetching drafts list.
 *  - disabled    — a 503 came back from /ocr/extractions or /ocr/invoice
 *                  (OCR_ENABLED=false in this environment).
 *  - list        — recent drafts + upload widget.
 *  - reviewing   — one draft loaded with editable fields + accept/reject.
 *
 * Low-confidence fields (below the response's ``low_confidence_threshold``)
 * are highlighted with an amber ring so the CA sees at a glance which
 * values need editing before Accept.
 *
 * P2.1 Step 5 scope: the surface above. E2E Playwright coverage lands
 * as Step 6.
 */
import { useCallback, useEffect, useState } from "react";
import { api, apiFormData, ApiError } from "@/lib/api";
import type {
  OcrAcceptResp,
  OcrExtraction,
  OcrExtractionListRow,
  OcrFieldName,
  OcrFieldValue,
  OcrRejectResp,
} from "@/lib/types";
import { formatTimestampIN } from "@/lib/format-date";


type PanelState =
  | { kind: "loading" }
  | { kind: "disabled" }
  | { kind: "list"; drafts: OcrExtractionListRow[] }
  | {
      kind: "reviewing";
      drafts: OcrExtractionListRow[];
      extraction: OcrExtraction;
      // Field overrides the CA has typed but not yet sent. Missing keys
      // fall back to the raw extraction value at accept time.
      edits: Partial<Record<OcrFieldName, string>>;
      inFlight: boolean;
    };


const FIELD_LABELS: Record<OcrFieldName, string> = {
  supplier_gstin: "Supplier GSTIN",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date (YYYY-MM-DD)",
  taxable_value_paise: "Taxable value (paise)",
  cgst_paise: "CGST (paise)",
  sgst_paise: "SGST (paise)",
  igst_paise: "IGST (paise)",
  total_paise: "Total (paise)",
  hsn_sac: "HSN / SAC",
};


const FIELD_ORDER: OcrFieldName[] = [
  "supplier_gstin",
  "invoice_number",
  "invoice_date",
  "hsn_sac",
  "taxable_value_paise",
  "cgst_paise",
  "sgst_paise",
  "igst_paise",
  "total_paise",
];


export function OcrPanel({
  gstinProfileId,
}: {
  gstinProfileId: string;
}) {
  const [panel, setPanel] = useState<PanelState>({ kind: "loading" });
  const [uploadMsg, setUploadMsg] = useState<{
    kind: "ok" | "error";
    text: string;
  } | null>(null);

  const reloadList = useCallback(async () => {
    try {
      const drafts = await api<OcrExtractionListRow[]>(
        `/ocr/extractions?gstin_profile_id=${gstinProfileId}`,
      );
      setPanel({ kind: "list", drafts });
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setPanel({ kind: "disabled" });
        return;
      }
      throw e;
    }
  }, [gstinProfileId]);

  useEffect(() => {
    reloadList();
  }, [reloadList]);

  async function openExtraction(id: string) {
    const extraction = await api<OcrExtraction>(`/ocr/extractions/${id}`);
    setPanel((p) => ({
      kind: "reviewing",
      drafts: "drafts" in p ? p.drafts : [],
      extraction,
      edits: {},
      inFlight: false,
    }));
  }

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    form.set("gstin_profile_id", gstinProfileId);
    setUploadMsg(null);
    try {
      const extraction = await apiFormData<OcrExtraction>(
        "/ocr/invoice",
        form,
      );
      setUploadMsg({
        kind: "ok",
        text: `Extracted ${extraction.source_filename} — review the draft below.`,
      });
      (e.target as HTMLFormElement).reset();
      // Reload the list, then jump straight into review for the new draft.
      await reloadList();
      await openExtraction(extraction.id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setPanel({ kind: "disabled" });
        return;
      }
      if (err instanceof ApiError) {
        setUploadMsg({
          kind: "error",
          text: `Upload failed (${err.status}): ${err.message}`,
        });
      } else {
        setUploadMsg({
          kind: "error",
          text: `Upload failed: ${(err as Error).message}`,
        });
      }
    }
  }

  if (panel.kind === "loading") {
    return <div className="text-ink-muted py-6">Loading OCR…</div>;
  }

  if (panel.kind === "disabled") {
    return (
      <div className="border border-rule rounded-md p-6 my-4 bg-amber-bg/40">
        <h3 className="font-semibold text-ink">
          OCR is not enabled for this environment
        </h3>
        <p className="mt-2 text-sm text-ink-muted">
          The <code>OCR_ENABLED</code> flag is off. Set it (and pick an
          adapter mode: <code>mock</code>, <code>pdfminer</code>) in the
          backend environment to preview the extraction flow.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 my-4">
      <UploadForm onSubmit={handleUpload} uploadMsg={uploadMsg} />

      <div>
        <h3 className="font-semibold text-ink mb-2">
          Recent drafts ({panel.drafts.length})
        </h3>
        {panel.drafts.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No OCR extractions yet. Upload one above.
          </p>
        ) : (
          <DraftsList
            drafts={panel.drafts}
            activeId={
              panel.kind === "reviewing" ? panel.extraction.id : null
            }
            onOpen={openExtraction}
          />
        )}
      </div>

      {panel.kind === "reviewing" && (
        <ReviewCard
          extraction={panel.extraction}
          edits={panel.edits}
          inFlight={panel.inFlight}
          onEdit={(field, value) =>
            setPanel((p) =>
              p.kind === "reviewing"
                ? { ...p, edits: { ...p.edits, [field]: value } }
                : p,
            )
          }
          onAccept={async () => {
            setPanel((p) =>
              p.kind === "reviewing" ? { ...p, inFlight: true } : p,
            );
            try {
              const body = Object.keys(panel.edits).length
                ? { edited_fields: panel.edits }
                : {};
              const resp = await api<OcrAcceptResp>(
                `/ocr/extractions/${panel.extraction.id}/accept`,
                { method: "POST", body },
              );
              setUploadMsg({
                kind: "ok",
                text: `Accepted — invoice ${resp.invoice_id.slice(0, 8)}… created.`,
              });
              await reloadList();
            } catch (err) {
              const msg =
                err instanceof ApiError
                  ? `Accept failed (${err.status}): ${err.message}`
                  : `Accept failed: ${(err as Error).message}`;
              setPanel((p) =>
                p.kind === "reviewing" ? { ...p, inFlight: false } : p,
              );
              setUploadMsg({ kind: "error", text: msg });
            }
          }}
          onReject={async () => {
            const reason =
              window.prompt("Reason for rejecting (optional):", "") || "";
            setPanel((p) =>
              p.kind === "reviewing" ? { ...p, inFlight: true } : p,
            );
            try {
              await api<OcrRejectResp>(
                `/ocr/extractions/${panel.extraction.id}/reject`,
                { method: "POST", body: { reason } },
              );
              setUploadMsg({ kind: "ok", text: "Rejected." });
              await reloadList();
            } catch (err) {
              const msg =
                err instanceof ApiError
                  ? `Reject failed (${err.status}): ${err.message}`
                  : `Reject failed: ${(err as Error).message}`;
              setPanel((p) =>
                p.kind === "reviewing" ? { ...p, inFlight: false } : p,
              );
              setUploadMsg({ kind: "error", text: msg });
            }
          }}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Upload form
// ---------------------------------------------------------------------------


function UploadForm({
  onSubmit,
  uploadMsg,
}: {
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  uploadMsg: { kind: "ok" | "error"; text: string } | null;
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="border border-rule rounded-md p-4 space-y-3"
      data-testid="ocr-upload-form"
    >
      <h3 className="font-semibold text-ink">Upload an invoice</h3>
      <div className="flex flex-wrap gap-3 items-center">
        <label className="text-sm text-ink-muted">
          Direction
          <select
            name="direction"
            required
            defaultValue="purchase"
            className="ml-2 border border-rule rounded-sm px-2 py-1"
          >
            <option value="purchase">Purchase</option>
            <option value="sale">Sale</option>
          </select>
        </label>
        <input
          type="file"
          name="file"
          required
          accept=".pdf,.png,.jpg,.jpeg,.webp,.txt"
          className="text-sm"
          data-testid="ocr-file-input"
        />
        <button
          type="submit"
          className="bg-accent text-white px-4 py-1.5 rounded-sm text-sm hover:opacity-90"
        >
          Extract fields
        </button>
      </div>
      {uploadMsg && (
        <p
          className={
            "text-sm " +
            (uploadMsg.kind === "ok"
              ? "text-green-fg"
              : "text-red-fg")
          }
        >
          {uploadMsg.text}
        </p>
      )}
    </form>
  );
}


// ---------------------------------------------------------------------------
// Drafts list
// ---------------------------------------------------------------------------


function DraftsList({
  drafts,
  activeId,
  onOpen,
}: {
  drafts: OcrExtractionListRow[];
  activeId: string | null;
  onOpen: (id: string) => void;
}) {
  return (
    <table className="w-full text-sm border border-rule">
      <thead className="bg-canvas-alt">
        <tr>
          <th className="text-left px-2 py-1">Filename</th>
          <th className="text-left px-2 py-1">Status</th>
          <th className="text-left px-2 py-1">Adapter</th>
          <th className="text-right px-2 py-1">Confidence</th>
          <th className="text-left px-2 py-1">Created</th>
          <th className="px-2 py-1" />
        </tr>
      </thead>
      <tbody>
        {drafts.map((d) => (
          <tr
            key={d.id}
            className={
              "border-t border-rule " +
              (activeId === d.id ? "bg-amber-bg/20" : "")
            }
          >
            <td className="px-2 py-1 font-mono text-xs">
              {d.source_filename}
            </td>
            <td className="px-2 py-1">
              <StatusPill status={d.status} />
            </td>
            <td className="px-2 py-1 text-ink-muted">{d.adapter}</td>
            <td className="px-2 py-1 text-right">
              {(d.overall_confidence * 100).toFixed(0)}%
            </td>
            <td className="px-2 py-1 text-ink-muted">
              {formatTimestampIN(d.created_at)}
            </td>
            <td className="px-2 py-1 text-right">
              <button
                onClick={() => onOpen(d.id)}
                className="text-accent hover:underline"
                data-testid={`ocr-open-${d.id}`}
              >
                Review
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}


function StatusPill({ status }: { status: string }) {
  const cls =
    status === "accepted"
      ? "bg-green-bg text-green-fg"
      : status === "rejected"
      ? "bg-red-bg text-red-fg"
      : "bg-amber-bg text-amber-fg";
  return (
    <span
      className={
        "inline-block text-xs px-1.5 py-0.5 rounded-sm border border-rule " +
        cls
      }
    >
      {status}
    </span>
  );
}


// ---------------------------------------------------------------------------
// Review card
// ---------------------------------------------------------------------------


function ReviewCard({
  extraction,
  edits,
  inFlight,
  onEdit,
  onAccept,
  onReject,
}: {
  extraction: OcrExtraction;
  edits: Partial<Record<OcrFieldName, string>>;
  inFlight: boolean;
  onEdit: (field: OcrFieldName, value: string) => void;
  onAccept: () => void;
  onReject: () => void;
}) {
  const locked = extraction.status !== "draft";
  return (
    <div
      className="border border-rule rounded-md p-4 space-y-4"
      data-testid="ocr-review-card"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-ink">
            Review draft — {extraction.source_filename}
          </h3>
          <p className="text-sm text-ink-muted">
            adapter <code>{extraction.adapter}</code> ·{" "}
            confidence{" "}
            <b>{(extraction.overall_confidence * 100).toFixed(0)}%</b> ·{" "}
            status <StatusPill status={extraction.status} />
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onReject}
            disabled={inFlight || locked}
            className="border border-rule px-3 py-1.5 rounded-sm text-sm hover:bg-canvas-alt disabled:opacity-50"
            data-testid="ocr-reject-btn"
          >
            Reject
          </button>
          <button
            onClick={onAccept}
            disabled={inFlight || locked}
            className="bg-accent text-white px-4 py-1.5 rounded-sm text-sm hover:opacity-90 disabled:opacity-50"
            data-testid="ocr-accept-btn"
          >
            {inFlight ? "Working…" : "Accept → create invoice"}
          </button>
        </div>
      </div>

      {extraction.warnings.length > 0 && (
        <ul className="text-sm bg-amber-bg/40 border border-rule rounded-sm px-3 py-2 space-y-1">
          {extraction.warnings.map((w, i) => (
            <li key={i} className="text-amber-fg">
              ⚠ {w}
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        {FIELD_ORDER.map((field) => (
          <FieldRow
            key={field}
            field={field}
            label={FIELD_LABELS[field]}
            extracted={extraction[field] as OcrFieldValue}
            edited={edits[field]}
            threshold={extraction.low_confidence_threshold}
            disabled={locked}
            onChange={(v) => onEdit(field, v)}
          />
        ))}
      </div>
    </div>
  );
}


function FieldRow({
  field,
  label,
  extracted,
  edited,
  threshold,
  disabled,
  onChange,
}: {
  field: OcrFieldName;
  label: string;
  extracted: OcrFieldValue;
  edited: string | undefined;
  threshold: number;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  const isLow = extracted.confidence < threshold;
  const current = edited !== undefined ? edited : extracted.value ?? "";
  const wasEdited = edited !== undefined && edited !== (extracted.value ?? "");
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-ink-muted">
        {label}{" "}
        <span
          className={
            "text-xs " + (isLow ? "text-amber-fg font-semibold" : "text-ink-muted/70")
          }
        >
          ({(extracted.confidence * 100).toFixed(0)}%)
        </span>
        {wasEdited && (
          <span className="text-xs text-accent ml-1">edited</span>
        )}
      </span>
      <input
        type="text"
        value={current}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`ocr-field-${field}`}
        className={
          "border rounded-sm px-2 py-1 font-mono text-xs " +
          (isLow
            ? "border-amber-fg ring-1 ring-amber-fg/40"
            : "border-rule") +
          (disabled ? " opacity-60" : "")
        }
      />
    </label>
  );
}
