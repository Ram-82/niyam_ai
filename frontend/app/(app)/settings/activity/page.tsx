"use client";
/**
 * /settings/activity — firm-wide immutable audit trail.
 *
 * Every state-mutating action lands in ``audit_log`` and surfaces here.
 * RLS on the backend guarantees a caller only ever sees their own firm's
 * rows, so this page can render whatever the API returns.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import { formatTimestampIN } from "@/lib/format-date";
import type { AuditRow } from "@/lib/types";


const ENTITY_OPTIONS = [
  "",
  "filing_run",
  "match_result",
  "validation_flag",
  "delivery_request",
  "supplier_contact",
  "client",
  "client_assignment",
  "user_invite",
  "import_job",
  "app_user",
] as const;


const ACTION_PREFIX_OPTIONS = [
  "",
  "filing.",
  "match.",
  "flag.",
  "auth.",
  "invite.",
  "import.",
  "supplier_contact.",
  "client.",
  "delivery.",
  "report.",
  "supplier_chase.",
  "gsp.",
] as const;


const inputCls =
  "border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink focus-visible:border-accent";


export default function ActivityPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [entityType, setEntityType] = useState<string>("");
  const [actionPrefix, setActionPrefix] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    setError(null);
    const params = new URLSearchParams();
    params.set("limit", "200");
    if (entityType) params.set("entity_type", entityType);
    if (actionPrefix) params.set("action_prefix", actionPrefix);
    api<AuditRow[]>(`/audit-log?${params.toString()}`)
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, [entityType, actionPrefix]);

  const columns: Column<AuditRow>[] = useMemo(
    () => [
      {
        key: "at",
        header: "When",
        cell: (r) => (
          <span className="font-mono text-xs">{formatTimestampIN(r.at)}</span>
        ),
        sortable: true,
        sortValue: (r) => r.at,
        width: "180px",
      },
      {
        key: "actor",
        header: "Actor",
        cell: (r) => (
          <span className="text-sm">
            {r.user_email || <span className="text-ink-muted italic">system</span>}
          </span>
        ),
        sortable: true,
        sortValue: (r) => r.user_email || "",
      },
      {
        key: "action",
        header: "Action",
        cell: (r) => (
          <span className="font-mono text-xs text-ink">{r.action}</span>
        ),
        sortable: true,
        sortValue: (r) => r.action,
      },
      {
        key: "entity",
        header: "Entity",
        cell: (r) => (
          <span className="text-xs">
            <span className="font-mono text-ink-muted">{r.entity_type}</span>
            {r.entity_id && (
              <span className="font-mono text-ink-muted ml-2">
                {r.entity_id.slice(0, 8)}
              </span>
            )}
          </span>
        ),
      },
      {
        key: "diff",
        header: "Detail",
        cell: (r) =>
          Object.keys(r.diff).length === 0 ? (
            <span className="text-ink-muted text-xs">—</span>
          ) : (
            <details>
              <summary className="cursor-pointer text-xs text-ink-muted">
                {Object.keys(r.diff).length} field
                {Object.keys(r.diff).length === 1 ? "" : "s"}
              </summary>
              <pre className="mt-1 text-xs font-mono max-w-md overflow-x-auto">
                {JSON.stringify(r.diff, null, 2)}
              </pre>
            </details>
          ),
      },
    ],
    []
  );

  const filterSummary = [
    entityType && `entity: ${entityType}`,
    actionPrefix && `action: ${actionPrefix}`,
  ]
    .filter(Boolean)
    .join(" · ") || "all activity";

  return (
    <>
      <PageHeader
        title="Activity"
        context={
          <span>
            Immutable log of every state-changing action on this firm.
            Append-only at the database layer.
          </span>
        }
      />

      <div className="flex flex-wrap gap-3 items-end">
        <label className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            Entity type
          </span>
          <select
            className={inputCls}
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            data-testid="audit-entity-select"
          >
            {ENTITY_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o || "all"}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
            Action prefix
          </span>
          <select
            className={inputCls}
            value={actionPrefix}
            onChange={(e) => setActionPrefix(e.target.value)}
            data-testid="audit-action-select"
          >
            {ACTION_PREFIX_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o || "all"}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Visible on screen as a filter summary line; also shown when printing. */}
      <p className="text-xs text-ink-muted">
        Showing {filterSummary}
        <span className="hidden print:inline">
          {" "}— printed {new Date().toLocaleDateString("en-IN")}
        </span>
      </p>

      <div className="mb-4" />

      {error && (
        <div className="bg-red-bg text-red-fg border border-rule rounded-md p-3 text-sm mb-4">
          {error}
        </div>
      )}

      {rows === null ? (
        <SkeletonTable rows={10} cols={5} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No activity for this filter"
          body="Actions land here as soon as they happen — try widening the filter."
        />
      ) : (
        <DataTable<AuditRow>
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          initialSort={{ key: "at", dir: "desc" }}
          rowTestId="audit-row"
          rowClass={(r) =>
            r.action.includes(".approve") ? "bg-stamp-tint" : ""
          }
        />
      )}
    </>
  );
}
