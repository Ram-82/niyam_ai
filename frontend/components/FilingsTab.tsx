"use client";
/**
 * FilingsTab — generate, review, approve, and mark-filed a GSTR-1/3B draft.
 *
 * State machine:  draft -> approved -> filed  (with unlock: approved -> draft)
 * Regenerate is only allowed in draft; the backend rejects otherwise (409).
 * "Filed" is terminal — the payload becomes read-only and no button flips it.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatPeriod, formatTimestampIN } from "@/lib/format-date";
import type { AuditRow, FilingRow } from "@/lib/types";


type Props = {
  gid: string;
  period: string;
  returnType: "GSTR1" | "GSTR3B";
};


const STATUS_PILL: Record<string, string> = {
  draft: "bg-amber-100 text-amber-900",
  approved: "bg-blue-100 text-blue-900",
  filed: "bg-green-100 text-green-900",
};


export function FilingsTab({ gid, period, returnType }: Props) {
  const [filing, setFiling] = useState<FilingRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filedInfo, setFiledInfo] = useState<{ arn: string | null; at: string } | null>(
    null,
  );
  const [arnDraft, setArnDraft] = useState("");
  const [showArnInput, setShowArnInput] = useState(false);

  async function loadFiling() {
    setError(null);
    try {
      const rows = await api<FilingRow[]>(
        `/gstins/${gid}/filings?period=${period}&return_type=${returnType}`,
      );
      const row = rows[0] ?? null;
      setFiling(row);
      if (row?.status === "filed") await loadFiledInfo(row.id);
      else setFiledInfo(null);
    } catch {
      // 404-ish; leave filing null so CA can Generate.
    }
  }

  async function loadFiledInfo(filingId: string) {
    try {
      const audits = await api<AuditRow[]>(
        `/audit-log?entity_type=filing_run&entity_id=${filingId}&action_prefix=filing.filed`,
      );
      if (audits.length > 0) {
        const latest = audits[0];
        const diff = latest.diff as { arn?: string | null; filed_at?: string };
        setFiledInfo({ arn: diff.arn ?? null, at: diff.filed_at ?? latest.at });
      }
    } catch {
      setFiledInfo(null);
    }
  }

  useEffect(() => {
    setFiling(null);
    setFiledInfo(null);
    loadFiling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gid, period, returnType]);

  async function run<T>(fn: () => Promise<T>) {
    setLoading(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
    } finally {
      setLoading(false);
    }
  }

  const generate = () =>
    run(async () => {
      const row = await api<FilingRow>("/filings/generate", {
        method: "POST",
        body: { gstin_profile_id: gid, period, return_type: returnType },
      });
      setFiling(row);
    });

  const approve = () =>
    run(async () => {
      if (!filing) return;
      const row = await api<FilingRow>(`/filings/${filing.id}/approve`, {
        method: "POST",
      });
      setFiling(row);
    });

  const unlock = () =>
    run(async () => {
      if (!filing) return;
      const row = await api<FilingRow>(`/filings/${filing.id}/unlock`, {
        method: "POST",
      });
      setFiling(row);
    });

  const markFiled = () =>
    run(async () => {
      if (!filing) return;
      const row = await api<FilingRow>(`/filings/${filing.id}/mark-filed`, {
        method: "POST",
        body: { arn: arnDraft.trim() || null },
      });
      setFiling(row);
      setShowArnInput(false);
      setArnDraft("");
      await loadFiledInfo(row.id);
    });

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

  const status = filing?.status ?? null;

  return (
    <div className="space-y-4">
      <div className="bg-paper-raised border border-rule rounded-md p-4 flex items-center gap-6 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wide text-ink-muted font-semibold flex items-center gap-2">
            {returnType} · {formatPeriod(period)}
            {status && (
              <span
                className={
                  "px-2 py-0.5 rounded text-[10px] font-bold uppercase " +
                  (STATUS_PILL[status] ?? "bg-slate-100 text-slate-900")
                }
                data-testid="filings-status"
              >
                {status}
              </span>
            )}
          </div>
          <div className="text-xs text-ink-muted mt-1">
            {filing
              ? `Updated ${formatTimestampIN(filing.updated_at)}`
              : "No draft yet."}
            {filedInfo && (
              <>
                {" · Filed "}
                <span className="font-mono text-ink">
                  {formatTimestampIN(filedInfo.at)}
                </span>
                {filedInfo.arn && (
                  <>
                    {" · ARN "}
                    <span className="font-mono text-ink">{filedInfo.arn}</span>
                  </>
                )}
              </>
            )}
          </div>
        </div>
        <div className="ml-auto flex gap-2 flex-wrap">
          {(status === null || status === "draft") && (
            <button
              onClick={generate}
              disabled={loading}
              className="px-3 py-2 text-sm rounded-md bg-accent text-white font-semibold disabled:opacity-50"
              data-testid="filings-generate"
            >
              {loading ? "Working…" : filing ? "Regenerate" : "Generate draft"}
            </button>
          )}
          {status === "draft" && filing && (
            <button
              onClick={approve}
              disabled={loading}
              className="px-3 py-2 text-sm rounded-md border border-accent text-accent font-semibold disabled:opacity-50"
              data-testid="filings-approve"
            >
              Approve
            </button>
          )}
          {status === "approved" && (
            <>
              <button
                onClick={unlock}
                disabled={loading}
                className="px-3 py-2 text-sm rounded-md border border-rule text-ink disabled:opacity-50"
                data-testid="filings-unlock"
              >
                Unlock
              </button>
              <button
                onClick={() => setShowArnInput((v) => !v)}
                disabled={loading}
                className="px-3 py-2 text-sm rounded-md bg-accent text-white font-semibold disabled:opacity-50"
                data-testid="filings-mark-filed"
              >
                Mark filed
              </button>
            </>
          )}
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

      {showArnInput && status === "approved" && (
        <div
          className="bg-paper-raised border border-rule rounded-md p-4 flex gap-2 items-center flex-wrap"
          data-testid="filings-arn-panel"
        >
          <label className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            ARN (optional)
          </label>
          <input
            type="text"
            className="border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink flex-1 min-w-[240px]"
            value={arnDraft}
            onChange={(e) => setArnDraft(e.target.value)}
            placeholder="AA010725012345Z"
            data-testid="filings-arn-input"
          />
          <button
            onClick={markFiled}
            disabled={loading}
            className="px-3 py-2 text-sm rounded-md bg-accent text-white font-semibold disabled:opacity-50"
            data-testid="filings-arn-confirm"
          >
            Confirm filed
          </button>
        </div>
      )}

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
            payload.
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
