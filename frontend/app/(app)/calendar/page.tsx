"use client";
/**
 * /calendar — upcoming GSTR-1 / GSTR-3B due dates across the firm.
 *
 * Backed by GET /calendar/upcoming. Groups rows into buckets (overdue,
 * this week, next week, later) so a CA can spot pressure at a glance
 * without hunting through the command-center table.
 */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import type { CalendarResponse, CalendarRow } from "@/lib/types";


type Bucket = "overdue" | "this_week" | "next_week" | "later";
const BUCKET_LABEL: Record<Bucket, string> = {
  overdue: "Overdue",
  this_week: "This week",
  next_week: "Next week",
  later: "Later",
};


function bucketOf(days_out: number): Bucket {
  if (days_out < 0) return "overdue";
  if (days_out <= 7) return "this_week";
  if (days_out <= 14) return "next_week";
  return "later";
}


function statusPill(status: CalendarRow["filing_status"]) {
  const map: Record<string, { label: string; cls: string }> = {
    draft:    { label: "Draft",    cls: "bg-amber-bg text-amber-fg" },
    approved: { label: "Approved", cls: "bg-accent-tint text-accent" },
    filed:    { label: "Filed",    cls: "bg-green-bg text-green-fg" },
  };
  const s = status ? map[status] : null;
  if (!s) {
    return (
      <span className="text-xs text-ink-muted">Not started</span>
    );
  }
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-sm ${s.cls}`}>
      {s.label}
    </span>
  );
}


function daysCell(days: number) {
  if (days < 0) {
    return (
      <span className="text-red-fg font-semibold tabular-nums">
        {-days}d overdue
      </span>
    );
  }
  if (days === 0) {
    return <span className="text-amber-fg font-semibold">Due today</span>;
  }
  if (days === 1) {
    return <span className="text-amber-fg font-semibold">Tomorrow</span>;
  }
  return <span className="tabular-nums">in {days}d</span>;
}


export default function CalendarPage() {
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CalendarResponse>("/calendar/upcoming")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  const groups = useMemo(() => {
    const out: Record<Bucket, CalendarRow[]> = {
      overdue: [], this_week: [], next_week: [], later: [],
    };
    for (const r of data?.rows ?? []) {
      // Filed rows are noise on a "what's coming" view; keep overdue
      // filed rows visible (rare, but if it happens we want to see it).
      if (r.filing_status === "filed" && r.days_out >= 0) continue;
      out[bucketOf(r.days_out)].push(r);
    }
    return out;
  }, [data]);

  const cols: Column<CalendarRow>[] = useMemo(
    () => [
      {
        key: "due",
        header: "Due",
        cell: (r) => daysCell(r.days_out),
        width: "8rem",
      },
      {
        key: "due_date",
        header: "Date",
        cell: (r) => new Date(r.due_date).toLocaleDateString(),
        width: "7rem",
      },
      {
        key: "return",
        header: "Return",
        cell: (r) => (
          <span className="text-xs font-semibold px-2 py-0.5 rounded-sm bg-accent-tint text-accent">
            {r.return_type}
          </span>
        ),
        width: "5.5rem",
      },
      {
        key: "period",
        header: "Period",
        cell: (r) => <span className="font-mono text-xs">{r.period}</span>,
        width: "5rem",
      },
      {
        key: "client",
        header: "Client",
        cell: (r) => r.client_trade_name || <span className="text-ink-muted">—</span>,
      },
      {
        key: "gstin",
        header: "GSTIN",
        cell: (r) => (
          <Link
            href={`/workspace/${r.gstin_profile_id}`}
            className="font-mono text-xs text-accent hover:text-accent-hover hover:underline"
          >
            {r.gstin}
          </Link>
        ),
        width: "12rem",
      },
      {
        key: "status",
        header: "Status",
        cell: (r) => statusPill(r.filing_status),
        width: "7rem",
      },
      {
        key: "reminders",
        header: "Reminders",
        cell: (r) =>
          r.reminders_sent > 0 ? (
            <span
              className="text-xs tabular-nums"
              title={`${r.reminders_sent} reminder email(s) already sent`}
            >
              {r.reminders_sent}
            </span>
          ) : (
            <span className="text-xs text-ink-muted">—</span>
          ),
        width: "6rem",
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="Calendar"
        context={
          data
            ? `Upcoming GSTR-1 / GSTR-3B deadlines (window: last ${data.lookback_days}d to next ${data.horizon_days}d).`
            : "Upcoming GSTR-1 / GSTR-3B deadlines across your firm's GSTINs."
        }
      />
      {error && (
        <p className="text-sm bg-red-bg text-red-fg border border-rule rounded-md px-3 py-2 max-w-[560px]">
          Load failed — {error}
        </p>
      )}
      {data === null && !error && <SkeletonTable rows={4} cols={6} />}
      {data && data.rows.length === 0 && (
        <EmptyState
          title="Nothing due in the window"
          body="No GSTR-1 / GSTR-3B deadlines within the current lookback + horizon. Add a GSTIN under Settings → Clients to see periods here."
          action={{ label: "Go to Settings", href: "/settings" }}
        />
      )}
      {data && data.rows.length > 0 && (
        <div className="space-y-8">
          {(["overdue", "this_week", "next_week", "later"] as Bucket[]).map(
            (b) => {
              const rows = groups[b];
              if (rows.length === 0) return null;
              return (
                <section key={b} className="space-y-2">
                  <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
                    {BUCKET_LABEL[b]}
                    <span className="text-xs text-ink-muted font-normal">
                      ({rows.length})
                    </span>
                  </h2>
                  <DataTable
                    columns={cols}
                    rows={rows}
                    rowKey={(r) =>
                      `${r.gstin_profile_id}-${r.period}-${r.return_type}`
                    }
                    rowTestId={`calendar-row-${b}`}
                  />
                </section>
              );
            },
          )}
        </div>
      )}
    </>
  );
}
