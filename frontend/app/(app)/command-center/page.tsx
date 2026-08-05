"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { defaultPeriod } from "@/lib/constants";
import { ITCCell, ITCHeader, ScoreCell } from "@/components/atoms";
import { ScoreBadge } from "@/components/ScoreBadge";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import { PeriodNav } from "@/components/PeriodNav";
import { StatTile } from "@/components/StatTile";
import { formatPeriod } from "@/lib/format-date";
import { formatDaysToDue } from "@/lib/format-days";
import { summarizeRows } from "@/lib/summarize-command-center";
import type { CommandCenterResponse, CommandCenterRow } from "@/lib/types";


export default function CommandCenterPage() {
  const [period, setPeriod] = useState(defaultPeriod());
  const [rows, setRows] = useState<CommandCenterRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    api<CommandCenterResponse>(`/command-center?period=${period}`)
      .then((r) => { if (!cancelled) setRows(r.rows); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [period]);

  const summary = useMemo(() => rows ? summarizeRows(rows) : null, [rows]);

  const columns: Column<CommandCenterRow>[] = [
    {
      key: "client",
      header: "Client",
      cell: (r) => <span className="text-ink">{r.client_name}</span>,
      sortable: true,
      sortValue: (r) => r.client_name.toLowerCase(),
    },
    {
      key: "gstin",
      header: "GSTIN",
      cell: (r) => <span className="font-mono text-xs text-ink-muted">{r.gstin}</span>,
      align: "left",
    },
    {
      key: "return",
      header: "Return",
      cell: (r) => r.return_type,
      sortable: true,
      sortValue: (r) => r.return_type,
      width: "6rem",
    },
    {
      key: "score",
      header: "Score",
      cell: (r) => <ScoreCell score={r.score} />,
      align: "right",
      sortable: true,
      sortValue: (r) => (r.score === null ? -1 : r.score),
      width: "7rem",
    },
    {
      key: "days",
      header: "Days to due",
      cell: (r) => <DaysToDueCell days={r.days_to_due_date} />,
      numeric: true,
      sortable: true,
      // Sort by raw number — overdue (negative) surfaces first when ascending.
      sortValue: (r) => r.days_to_due_date ?? 999,
      width: "10rem",
    },
    {
      key: "itc",
      header: <ITCHeader label="ITC at risk" />,
      cell: (r) => <ITCCell paise={r.itc_at_risk_paise} />,
      numeric: true,
      sortable: true,
      sortValue: (r) => r.itc_at_risk_paise,
      width: "11rem",
    },
    {
      key: "blockers",
      header: "Blockers (CA · Client)",
      cell: (r) => <BlockersSplit ca={r.blockers_ca} client={r.blockers_client} total={r.blockers_count} />,
      // Right-align but not numeric-font — the labels are letters.
      align: "right",
      sortable: true,
      sortValue: (r) => r.blockers_count,
      width: "10rem",
    },
    {
      key: "actions",
      header: "",
      cell: (r) => (
        <Link
          href={`/workspace/${r.gstin_profile_id}?period=${r.period}&return_type=${r.return_type}&client=${encodeURIComponent(r.client_name)}&gstin=${r.gstin}`}
          className="inline-flex items-center gap-1 text-accent hover:text-accent-hover text-sm font-semibold whitespace-nowrap"
          data-testid="cc-drill"
        >
          Open <span aria-hidden="true">→</span>
        </Link>
      ),
      align: "right",
      width: "5rem",
    },
  ];

  return (
    <>
      <PageHeader
        title="Command center"
        context="Every client × GSTIN × return, ranked by readiness × deadline."
        actions={<PeriodNav value={period} onChange={setPeriod} />}
      />

      {/* Summary strip — each tile carries a one-line comment on its
          aggregation basis. See lib/summarize-command-center.ts for the
          canonical rules and the unit tests that guard them. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Basis: row count (client × GSTIN × return_type). */}
        <StatTile
          label="Returns this period"
          value={summary ? summary.totalReturns : "—"}
        />
        {/* Basis: mean of non-null scores across table rows. */}
        <StatTile
          label="Avg readiness"
          value={
            summary?.avgScore !== null && summary?.avgScore !== undefined ? (
              <ScoreBadge score={summary.avgScore} size="sm" testId="summary-avg-score" />
            ) : (
              <span className="italic text-grey-fg text-sm">Not yet scored</span>
            )
          }
        />
        {/* Basis: unique (gstin_profile, period) recon summaries — deduped
            across return_type rows (GSTR1+GSTR3B share one recon pool). */}
        <StatTile
          label="Total ITC at risk"
          value={
            summary ? (
              <span className="text-red-fg">
                <ITCCell paise={summary.totalItcAtRiskPaise} />
              </span>
            ) : "—"
          }
        />
        {/* Basis: row count where days_to_due < 0 (each return_type has
            its own deadline; overdue GSTR1 and overdue GSTR3B are distinct). */}
        <StatTile
          label="Overdue returns"
          value={
            summary ? (
              <span className={summary.overdueReturns > 0 ? "text-red-fg" : ""}>
                {summary.overdueReturns}
              </span>
            ) : "—"
          }
          emphasize={summary && summary.overdueReturns > 0 ? "red" : null}
        />
      </div>

      {error && (
        <p className="text-sm text-red-fg bg-red-bg border border-rule rounded-md px-3 py-2">
          Couldn't load command center rows — {error}. Retry after
          checking that the API service is reachable.
        </p>
      )}

      {/* Row-count strip above the table */}
      <div className="flex items-center text-xs text-ink-muted">
        <span>
          {rows ? `${rows.length} return${rows.length === 1 ? "" : "s"}` : "…"}
          {" · "}{formatPeriod(period)}
        </span>
      </div>

      {rows === null && !error && <SkeletonTable rows={6} cols={8} />}

      {rows && (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => `${r.gstin_profile_id}-${r.return_type}`}
          rowTestId="cc-row"
          initialSort={{ key: "score", dir: "asc" }}
          emptyState={
            <EmptyState
              title="No clients yet"
              body={`No client × GSTIN combinations exist in your firm for ${formatPeriod(period)}. Add a client (and its GSTIN) in Settings, then upload a purchase register to see rows here.`}
              action={{ label: "Go to Settings", href: "/settings" }}
            />
          }
        />
      )}
    </>
  );
}


function BlockersSplit({ ca, client, total }: { ca: number; client: number; total: number }) {
  if (total === 0) return <span className="text-ink-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-1 justify-end">
      {ca > 0 && (
        <span
          className="text-xs font-mono font-semibold px-1.5 py-0.5 rounded-sm bg-accent-tint text-accent"
          title={`${ca} blocker${ca === 1 ? "" : "s"} owned by CA`}
        >
          {ca} CA
        </span>
      )}
      {client > 0 && (
        <span
          className="text-xs font-mono font-semibold px-1.5 py-0.5 rounded-sm bg-grey-bg text-ink"
          title={`${client} blocker${client === 1 ? "" : "s"} owned by client`}
        >
          {client} client
        </span>
      )}
    </span>
  );
}


function DaysToDueCell({ days }: { days: number | null }) {
  const d = formatDaysToDue(days);
  if (d.tone === "empty") return <span className="text-ink-muted">{d.label}</span>;
  if (d.tone === "plain") return <span>{d.label}</span>;
  const cls =
    d.tone === "red-pill"
      ? "bg-red-bg text-red-fg"
      : "bg-amber-bg text-amber-fg";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-semibold ${cls}`}>
      {d.label}
    </span>
  );
}
