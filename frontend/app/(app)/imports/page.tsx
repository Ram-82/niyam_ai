"use client";
import { useEffect, useState } from "react";
import { api, apiFormData } from "@/lib/api";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import { formatPeriod, formatTimestampIN } from "@/lib/format-date";


type UnifiedRow = {
  source_kind: "upload" | "gsp_api";
  id: string;
  label: string;
  status: string;
  filename: string | null;
  period: string | null;
  at: string;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  error_message: string | null;
  error_kind: string | null;
};


const inputCls =
  "block border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink " +
  "focus-visible:border-accent";
const btnPrimaryCls =
  "px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm " +
  "hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50";


export default function ImportsPage() {
  const [jobs, setJobs] = useState<UnifiedRow[] | null>(null);
  const [gid, setGid] = useState("");
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function refresh() {
    const rows = await api<UnifiedRow[]>("/imports/unified/list");
    setJobs(rows);
  }
  useEffect(() => {
    refresh();
  }, []);

  async function uploadInvoices(
    e: React.FormEvent<HTMLFormElement>,
    direction: "purchase" | "sale"
  ) {
    e.preventDefault();
    setMessage(null);
    try {
      const form = new FormData(e.currentTarget);
      form.set("direction", direction);
      if (gid) form.set("gstin_profile_id", gid);
      await apiFormData("/imports/invoices", form);
      setMessage({ kind: "ok", text: `${direction} upload queued.` });
      refresh();
    } catch (err) {
      setMessage({ kind: "error", text: `Upload failed — ${err}. Check the GSTIN profile ID and try again.` });
    }
  }

  async function upload2b(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setMessage(null);
    try {
      const form = new FormData(e.currentTarget);
      if (gid) form.set("gstin_profile_id", gid);
      await apiFormData("/imports/gstr2b", form);
      setMessage({ kind: "ok", text: "2B upload queued." });
      refresh();
    } catch (err) {
      setMessage({ kind: "error", text: `Upload failed — ${err}. Check the file is a valid 2B JSON and the period matches.` });
    }
  }

  const columns: Column<UnifiedRow>[] = [
    {
      key: "source",
      header: "Source",
      cell: (j) => <SourceChip source={j.source_kind} />,
      width: "8rem",
    },
    {
      key: "label",
      header: "Kind / filename",
      cell: (j) => (
        <span className="font-mono text-xs">
          {j.source_kind === "upload" ? j.filename || j.label : j.label}
        </span>
      ),
    },
    {
      key: "period",
      header: "Period",
      cell: (j) => formatPeriod(j.period),
      width: "7rem",
    },
    {
      key: "at",
      header: "At",
      cell: (j) => (
        <span className="font-mono text-xs">
          {formatTimestampIN(j.at)}
        </span>
      ),
      width: "12rem",
    },
    {
      key: "status",
      header: "Status",
      cell: (j) => <StatusPill status={j.status} />,
      width: "9rem",
    },
    {
      key: "counts",
      header: "Accepted / rejected / dup",
      cell: (j) =>
        j.source_kind === "upload" ? (
          <span className="font-mono text-xs">
            {j.accepted_rows} / {j.rejected_rows} / {j.duplicate_rows}
          </span>
        ) : (
          <span className="text-xs text-ink-muted">—</span>
        ),
      numeric: true,
      width: "13rem",
    },
  ];

  return (
    <>
      <PageHeader
        title="Imports"
        context="Upload purchase / sales registers or GSTR-2B JSON. Files are queued; rejects come back as a downloadable CSV."
      />

      {message && (
        <p
          className={
            "text-sm border rounded-md px-3 py-2 " +
            (message.kind === "ok"
              ? "bg-green-bg text-green-fg border-rule"
              : "bg-red-bg text-red-fg border-rule")
          }
        >
          {message.text}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-6 items-start">
        {/* Intake column */}
        <aside className="bg-paper-raised border border-rule rounded-md overflow-hidden">
          <div className="px-6 py-3 border-b border-rule bg-paper">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Intake
            </h2>
          </div>
          <div className="p-6 space-y-4">
            <label className="block">
              <span className="text-sm font-semibold text-ink">GSTIN profile ID</span>
              <input
                className={"mt-1 w-full font-mono " + inputCls}
                value={gid}
                onChange={(e) => setGid(e.target.value)}
                placeholder="uuid"
              />
            </label>

            <form
              className="flex items-center gap-3 flex-wrap"
              onSubmit={(e) => uploadInvoices(e, "purchase")}
            >
              <input type="file" name="file" required className="text-sm" />
              <button className={btnPrimaryCls}>Upload purchase register</button>
            </form>

            <form
              className="flex items-center gap-3 flex-wrap"
              onSubmit={(e) => uploadInvoices(e, "sale")}
            >
              <input type="file" name="file" required className="text-sm" />
              <button className={btnPrimaryCls}>Upload sales register</button>
            </form>

            <form className="flex items-center gap-3 flex-wrap" onSubmit={upload2b}>
              <input type="file" name="file" required accept=".json,application/json" className="text-sm" />
              <input
                type="text"
                name="period"
                required
                pattern="[0-9]{6}"
                placeholder="e.g. 202607"
                aria-label="Period (six-digit YYYYMM, e.g. 202607 for July 2026)"
                title="Six digits: YYYYMM. Example: 202607 = July 2026."
                className={"font-mono w-36 " + inputCls}
              />
              <button className={btnPrimaryCls}>Upload GSTR-2B JSON</button>
            </form>

            <p
              className="text-xs text-ink-muted italic"
              title="Live GSP pulls are triggered from a client's workspace via the Connections panel — they land in this same list, labeled Live GSP pull."
            >
              Live GSP pulls happen from the client workspace.
            </p>
          </div>
        </aside>

        {/* Ledger column */}
        <section className="bg-paper-raised border border-rule rounded-md overflow-hidden">
          <div className="px-6 py-3 border-b border-rule bg-paper">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Recent jobs
            </h2>
          </div>
          {jobs === null && (
            <div className="p-4">
              <SkeletonTable rows={4} cols={5} />
            </div>
          )}
          {jobs !== null && (
            <DataTable
              columns={columns}
              rows={jobs}
              rowKey={(j) => j.id}
              expandRow={(j) => {
                const hasError = !!(j.error_message || j.error_kind);
                const hasRejects = j.source_kind === "upload" && j.rejected_rows > 0;
                if (!hasError && !hasRejects) return null;
                return (
                  <div className="space-y-1 text-xs">
                    {j.error_message && (
                      <p className="text-red-fg font-mono whitespace-pre-wrap break-all">
                        {j.error_message}
                      </p>
                    )}
                    {!j.error_message && j.error_kind && (
                      <p className="text-red-fg font-mono">{j.error_kind}</p>
                    )}
                    {hasRejects && (
                      <p className="text-ink-muted">
                        {j.accepted_rows} accepted · {j.rejected_rows} rejected · {j.duplicate_rows} duplicate
                        {j.rejected_rows > 0 && (
                          <a
                            href={`${process.env.NIYAM_API_BASE || "http://localhost:8000"}/imports/${j.id}/errors.csv`}
                            className="ml-3 text-accent hover:underline font-semibold"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Download errors.csv
                          </a>
                        )}
                      </p>
                    )}
                  </div>
                );
              }}
              emptyState={
                <EmptyState
                  title="No imports yet"
                  body="Upload a purchase or sales register (CSV/XLSX), or a GSTR-2B JSON, to start a background job. Completed jobs appear here with per-row accept/reject counts and a downloadable error report."
                />
              }
            />
          )}
        </section>
      </div>
    </>
  );
}


function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued:           "bg-grey-bg text-ink-muted",
    running:          "bg-accent-tint text-accent",
    completed:        "bg-green-bg text-green-fg",
    succeeded:        "bg-green-bg text-green-fg",
    failed:           "bg-red-bg text-red-fg",
    retry_scheduled:  "bg-amber-bg text-amber-fg",
  };
  const cls = map[status] || "bg-grey-bg text-ink-muted";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-sm ${cls}`}>
      {status}
    </span>
  );
}


function SourceChip({ source }: { source: "upload" | "gsp_api" }) {
  if (source === "gsp_api") {
    return (
      <span
        className="text-xs font-semibold px-2 py-0.5 rounded-sm bg-accent-tint text-accent"
        data-testid="source-gsp"
      >
        Live GSP pull
      </span>
    );
  }
  return (
    <span
      className="text-xs font-semibold px-2 py-0.5 rounded-sm bg-grey-bg text-ink-muted"
      data-testid="source-upload"
    >
      Upload
    </span>
  );
}
