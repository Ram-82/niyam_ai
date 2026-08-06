"use client";
/**
 * FilingsTab — generate + preview a GSTR-1 or GSTR-3B draft JSON.
 *
 * The payload lands in JSONB on the server; we render it as pretty JSON
 * in a <pre>, and offer a Download button that packages it as a .json
 * file so the CA can hand it to whichever GSTN upload path they use
 * (portal, offline tool, or GSP once we have live credentials).
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatPeriod, formatTimestampIN } from "@/lib/format-date";
import type { FilingRow } from "@/lib/types";


type Props = {
  gid: string;
  period: string;
  returnType: "GSTR1" | "GSTR3B";
};


export function FilingsTab({ gid, period, returnType }: Props) {
  const [filing, setFiling] = useState<FilingRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch the existing draft for (gid, period, return_type) so the CA
  // returns to what they had rather than a blank slate. 404 is fine —
  // means "nothing generated yet."
  useEffect(() => {
    setFiling(null);
    setError(null);
    api<FilingRow[]>(
      `/gstins/${gid}/filings?period=${period}&return_type=${returnType}`
    )
      .then((rows) => {
        if (rows.length > 0) setFiling(rows[0]);
      })
      .catch(() => {
        // Non-fatal — user can still click Generate.
      });
  }, [gid, period, returnType]);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const row = await api<FilingRow>("/filings/generate", {
        method: "POST",
        body: {
          gstin_profile_id: gid,
          period,
          return_type: returnType,
        },
      });
      setFiling(row);
    } catch (e) {
      const msg =
        e instanceof ApiError ? `${e.status}: ${e.message}` : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function download() {
    if (!filing?.payload) return;
    const blob = new Blob([JSON.stringify(filing.payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${returnType}-${period}-${filing.id.slice(0, 8)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="bg-paper-raised border border-rule rounded-md p-4 flex items-center gap-6 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            {returnType} · {formatPeriod(period)}
          </div>
          <div className="text-xs text-ink-muted mt-1">
            {filing
              ? `Status: ${filing.status} · updated ${formatTimestampIN(
                  filing.updated_at
                )}`
              : "No draft yet."}
          </div>
        </div>
        <div className="ml-auto flex gap-2">
          <button
            onClick={generate}
            disabled={loading}
            className="px-3 py-2 text-sm rounded-md bg-accent text-white font-semibold disabled:opacity-50"
            data-testid="filings-generate"
          >
            {loading ? "Generating…" : filing ? "Regenerate" : "Generate draft"}
          </button>
          <button
            onClick={download}
            disabled={!filing?.payload}
            className="px-3 py-2 text-sm rounded-md border border-rule text-ink disabled:opacity-50"
            data-testid="filings-download"
          >
            Download .json
          </button>
        </div>
      </div>

      {error && (
        <div
          className="bg-red-bg text-red-fg border border-rule rounded-md p-3 text-sm"
          data-testid="filings-error"
        >
          {error}
        </div>
      )}

      {filing?.payload && (
        <div>
          <div className="text-xs text-ink-muted mb-2">
            Rule pack{" "}
            <span className="font-mono text-ink">
              {filing.rule_pack_version}
            </span>
            . Sections deferred are listed under{" "}
            <span className="font-mono">_meta.sections_deferred</span> in the
            payload — CA must handle them via the portal until Niyam captures
            the underlying data.
          </div>
          <pre
            className="bg-paper-raised border border-rule rounded-md p-4 text-xs font-mono overflow-x-auto max-h-[500px] overflow-y-auto"
            data-testid="filings-payload"
          >
            {JSON.stringify(filing.payload, null, 2)}
          </pre>
        </div>
      )}

      {!filing && !error && (
        <div className="text-sm text-ink-muted">
          Click <span className="font-semibold">Generate draft</span> to build
          the {returnType} JSON for this period from your reconciled data.
        </div>
      )}
    </div>
  );
}
