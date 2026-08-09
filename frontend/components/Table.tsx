/**
 * Shared table primitives — one ruled-book treatment used everywhere.
 *
 * ``<DataTable>`` gives you:
 *   - sticky header
 *   - hover row
 *   - dense but readable row height (36px)
 *   - opt-in sortable columns (visible sort indicator)
 *   - right-aligned + tabular-nums helper for numeric columns
 *
 * Callers pass typed columns + rows. Nothing about this component
 * cares about domain — command center, invoices, flags, matches all
 * render through it.
 */
"use client";
import { Fragment, useMemo, useState } from "react";


export type Column<T> = {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  align?: "left" | "right";
  numeric?: boolean;                   // triggers font-mono + tabular-nums
  sortable?: boolean;
  sortValue?: (row: T) => number | string | null;
  width?: string;                      // css width — leave undefined for auto
};


type SortState = { key: string; dir: "asc" | "desc" } | null;


export function DataTable<T>({
  columns,
  rows,
  emptyState,
  rowTestId,
  initialSort,
  rowKey,
  onRowClick,
  expandRow,
  rowClass,
}: {
  columns: Column<T>[];
  rows: T[];
  emptyState?: React.ReactNode;
  rowTestId?: string;
  initialSort?: SortState;
  rowKey: (row: T, i: number) => string;
  onRowClick?: (row: T) => void;
  expandRow?: (row: T) => React.ReactNode;
  rowClass?: (row: T) => string;
}) {
  const [sort, setSort] = useState<SortState>(initialSort ?? null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col || !col.sortValue) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const va = col.sortValue!(a);
      const vb = col.sortValue!(b);
      // Nulls first when ascending, last when descending.
      if (va === null && vb === null) return 0;
      if (va === null) return sort.dir === "asc" ? -1 : 1;
      if (vb === null) return sort.dir === "asc" ? 1 : -1;
      if (va < vb) return sort.dir === "asc" ? -1 : 1;
      if (va > vb) return sort.dir === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, columns, sort]);

  function toggle(colKey: string) {
    setSort((cur) => {
      if (cur?.key !== colKey) return { key: colKey, dir: "asc" };
      if (cur.dir === "asc") return { key: colKey, dir: "desc" };
      return null;
    });
  }

  if (rows.length === 0 && emptyState) {
    return <div className="bg-paper-raised border border-rule rounded-md">{emptyState}</div>;
  }

  return (
    <div className="bg-paper-raised border border-rule rounded-md overflow-hidden">
      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 z-10 bg-paper text-ink-muted">
            <tr className="h-10">
              {columns.map((c) => {
                const isSorted = sort?.key === c.key;
                const align = c.align ?? (c.numeric ? "right" : "left");
                return (
                  <th
                    key={c.key}
                    className={
                      "text-xs font-semibold uppercase tracking-wide " +
                      "px-4 py-2 border-b border-rule select-none " +
                      (align === "right" ? "text-right" : "text-left") +
                      (c.sortable ? " cursor-pointer hover:text-ink" : "")
                    }
                    style={c.width ? { width: c.width } : undefined}
                    onClick={c.sortable ? () => toggle(c.key) : undefined}
                    aria-sort={
                      isSorted
                        ? sort.dir === "asc" ? "ascending" : "descending"
                        : c.sortable ? "none" : undefined
                    }
                  >
                    <span
                      className={
                        "inline-flex items-center gap-1 " +
                        (align === "right" ? "float-right" : "")
                      }
                    >
                      {c.header}
                      {c.sortable && (
                        <SortGlyph state={isSorted ? sort.dir : null} />
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => {
              const key = rowKey(row, i);
              const isExpanded = expandedKey === key;
              const expandContent = expandRow?.(row);
              const hasExpand = expandContent != null;
              const extraCls = rowClass?.(row) ?? "";
              const clickable = !!(onRowClick || hasExpand);
              return (
                <Fragment key={key}>
                  <tr
                    data-testid={rowTestId}
                    onClick={() => {
                      if (hasExpand) {
                        setExpandedKey(isExpanded ? null : key);
                      } else if (onRowClick) {
                        onRowClick(row);
                      }
                    }}
                    className={
                      "h-[34px] border-b border-rule last:border-b-0 hover:bg-row-hover transition-colors duration-fast" +
                      (clickable ? " cursor-pointer" : "") +
                      (extraCls ? " " + extraCls : "")
                    }
                  >
                    {columns.map((c) => {
                      const align = c.align ?? (c.numeric ? "right" : "left");
                      return (
                        <td
                          key={c.key}
                          className={
                            "px-4 py-2 align-middle whitespace-nowrap " +
                            (align === "right" ? "text-right" : "text-left") +
                            (c.numeric ? " font-mono" : "")
                          }
                        >
                          {c.cell(row)}
                        </td>
                      );
                    })}
                  </tr>
                  {isExpanded && hasExpand && (
                    <tr className="border-b border-rule last:border-b-0">
                      <td
                        colSpan={columns.length}
                        className="px-4 py-3 bg-paper"
                      >
                        {expandContent}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function SortGlyph({ state }: { state: "asc" | "desc" | null }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      <path
        d="M5 1 L9 5 H1 Z"
        fill={state === "asc" ? "var(--accent)" : "var(--rule-strong)"}
      />
      <path
        d="M5 9 L1 5 H9 Z"
        fill={state === "desc" ? "var(--accent)" : "var(--rule-strong)"}
      />
    </svg>
  );
}
