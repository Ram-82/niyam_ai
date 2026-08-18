"use client";

import { useState, type CSSProperties } from "react";
import Link from "next/link";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { LoadingState } from "@/components/v2/ui/LoadingState";
import {
  ACTION_PREFIXES,
  ENTITY_TYPES,
  EMPTY_FILTERS,
  formatAbsolute,
  formatRelative,
  humanizeAction,
  humanizeEntityType,
  toneFor,
  useAuditLog,
  type AuditFilters,
  type AuditRow,
} from "./useAuditLog";

const CARD: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-app-card)",
  boxShadow: "var(--shadow-card)",
};

const LABEL: CSSProperties = {
  fontSize: "var(--fs-label)",
  lineHeight: "var(--lh-label)",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

const TONE_STYLE: Record<"success" | "danger" | "warning" | "neutral", CSSProperties> = {
  success: { background: "var(--success-soft)", color: "var(--success)" },
  danger: { background: "var(--danger-soft)", color: "var(--danger)" },
  warning: { background: "var(--warning-soft)", color: "var(--warning)" },
  neutral: { background: "var(--muted-soft)", color: "var(--text-secondary)" },
};

export default function AuditLogPage() {
  const state = useAuditLog();
  const { rows, filters, loading, loadingMore, error, hasMore, setFilters, reload, loadMore } = state;
  const [expanded, setExpanded] = useState<string | null>(null);

  const activeFilterCount =
    (filters.entity_type ? 1 : 0) +
    (filters.action_prefix ? 1 : 0) +
    (filters.since ? 1 : 0) +
    (filters.until ? 1 : 0);

  return (
    <div style={{ padding: 32, display: "flex", flexDirection: "column", gap: 24, maxWidth: 1504, width: "100%" }}>
      <header style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1 style={{
            margin: 0,
            fontSize: "var(--fs-display)",
            lineHeight: "var(--lh-display)",
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-display)",
            color: "var(--text-primary)",
          }}>
            Audit log
          </h1>
          <p style={{ margin: 0, fontSize: "var(--fs-body)", lineHeight: "var(--lh-body)", color: "var(--text-secondary)" }}>
            Immutable record of firm activity — filings, auth events, settings changes. Firm-scoped.
          </p>
        </div>
        <Link
          href="/v2/dashboard"
          className="v2-focus"
          style={{ fontSize: 13, color: "var(--text-secondary)", textDecoration: "none" }}
        >
          ← Back to dashboard
        </Link>
      </header>

      {error && <ErrorBanner message={`Could not load audit log: ${error}`} onRetry={reload} />}

      <FilterBar filters={filters} activeCount={activeFilterCount} onChange={setFilters} />

      <section style={{ ...CARD, overflow: "hidden" }}>
        <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            Events
          </h2>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {loading
              ? "Loading…"
              : rows.length === 0
              ? "No events"
              : `${rows.length}${hasMore ? "+" : ""} event${rows.length === 1 ? "" : "s"} shown`}
          </span>
        </div>

        {loading && rows.length === 0 ? (
          <LoadingState message="Loading audit log…" />
        ) : rows.length === 0 ? (
          <EmptyState
            message={activeFilterCount > 0 ? "No events match these filters." : "No events recorded yet."}
            hint={activeFilterCount > 0 ? "Clear filters to see everything." : undefined}
          />
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 180 }} />
              <col style={{ width: 220 }} />
              <col style={{ width: 160 }} />
              <col style={{ width: 220 }} />
              <col />
              <col style={{ width: 60 }} />
            </colgroup>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <Th>When</Th>
                <Th>Action</Th>
                <Th>Entity</Th>
                <Th>Actor</Th>
                <Th>Details</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row
                  key={row.id}
                  row={row}
                  expanded={expanded === row.id}
                  onToggle={() => setExpanded((cur) => (cur === row.id ? null : row.id))}
                />
              ))}
            </tbody>
          </table>
        )}

        {rows.length > 0 && (
          <div style={{ padding: "12px 24px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "center" }}>
            {hasMore ? (
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="v2-focus"
                style={{
                  padding: "8px 16px",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-input)",
                  background: loadingMore ? "var(--muted-soft)" : "var(--surface)",
                  color: "var(--text-primary)",
                  fontSize: 13,
                  fontWeight: "var(--fw-medium)",
                  cursor: loadingMore ? "not-allowed" : "pointer",
                }}
              >
                {loadingMore ? "Loading…" : "Load older events"}
              </button>
            ) : (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>End of log.</span>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Th({ children }: { children?: React.ReactNode }) {
  return (
    <th style={{ padding: "10px 24px", textAlign: "left", ...LABEL }}>
      {children}
    </th>
  );
}

function Row({ row, expanded, onToggle }: { row: AuditRow; expanded: boolean; onToggle: () => void }) {
  const tone = toneFor(row.action);
  const hasDiff = row.diff && Object.keys(row.diff).length > 0;
  return (
    <>
      <tr style={{ borderBottom: expanded ? "0" : "1px solid var(--border)" }}>
        <td style={{ padding: "12px 24px", color: "var(--text-secondary)", fontSize: 13 }}>
          <span title={formatAbsolute(row.at)}>{formatRelative(row.at)}</span>
        </td>
        <td style={{ padding: "12px 24px" }}>
          <span
            className="mono"
            style={{
              padding: "3px 8px",
              borderRadius: "var(--radius-chip)",
              fontSize: 11,
              lineHeight: "16px",
              fontWeight: "var(--fw-medium)",
              ...TONE_STYLE[tone],
            }}
          >
            {row.action}
          </span>
        </td>
        <td style={{ padding: "12px 24px", color: "var(--text-primary)", fontSize: 13 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span>{humanizeEntityType(row.entity_type)}</span>
            {row.entity_id && (
              <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {row.entity_id.slice(0, 8)}…
              </span>
            )}
          </div>
        </td>
        <td style={{ padding: "12px 24px", color: "var(--text-secondary)", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {row.user_email ?? <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>system</span>}
        </td>
        <td style={{ padding: "12px 24px", color: "var(--text-muted)", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {hasDiff ? summarizeDiff(row.diff) : <span>—</span>}
        </td>
        <td style={{ padding: "12px 24px", textAlign: "right" }}>
          {hasDiff && (
            <button
              type="button"
              onClick={onToggle}
              className="v2-focus"
              aria-label={expanded ? "Collapse diff" : "Expand diff"}
              style={{
                width: 24,
                height: 24,
                border: "1px solid var(--border)",
                borderRadius: 4,
                background: "var(--surface)",
                color: "var(--text-secondary)",
                fontSize: 12,
                cursor: "pointer",
                padding: 0,
              }}
            >
              {expanded ? "−" : "+"}
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid var(--border)" }}>
          <td colSpan={6} style={{ padding: "0 24px 16px" }}>
            <pre className="mono" style={{
              margin: 0,
              padding: 12,
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
              lineHeight: "18px",
              color: "var(--text-primary)",
              overflow: "auto",
              maxHeight: 320,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}>
              {JSON.stringify(row.diff, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

function summarizeDiff(diff: Record<string, unknown>): string {
  const keys = Object.keys(diff);
  if (keys.length === 0) return "—";
  const first = keys.slice(0, 3).join(", ");
  return keys.length > 3 ? `${first} +${keys.length - 3} more` : first;
}

/* ---------------------------- Filter bar ---------------------------- */

function FilterBar({
  filters, activeCount, onChange,
}: {
  filters: AuditFilters;
  activeCount: number;
  onChange: (next: AuditFilters) => void;
}) {
  return (
    <section style={{ ...CARD, padding: 16, display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
      <FilterField label="Entity type">
        <select
          value={filters.entity_type}
          onChange={(e) => onChange({ ...filters, entity_type: e.target.value })}
          className="v2-focus"
          style={SELECT_STYLE}
        >
          <option value="">All entities</option>
          {ENTITY_TYPES.map((et) => (
            <option key={et} value={et}>{humanizeEntityType(et)}</option>
          ))}
        </select>
      </FilterField>

      <FilterField label="Action prefix">
        <select
          value={ACTION_PREFIXES.includes(filters.action_prefix as (typeof ACTION_PREFIXES)[number]) ? filters.action_prefix : ""}
          onChange={(e) => onChange({ ...filters, action_prefix: e.target.value })}
          className="v2-focus"
          style={SELECT_STYLE}
        >
          <option value="">All actions</option>
          {ACTION_PREFIXES.map((p) => (
            <option key={p} value={p}>{humanizeAction(p.replace(/\.$/, ""))} events</option>
          ))}
        </select>
      </FilterField>

      <FilterField label="From">
        <input
          type="date"
          value={filters.since}
          onChange={(e) => onChange({ ...filters, since: e.target.value })}
          className="v2-focus"
          style={INPUT_STYLE}
        />
      </FilterField>

      <FilterField label="To">
        <input
          type="date"
          value={filters.until}
          onChange={(e) => onChange({ ...filters, until: e.target.value })}
          className="v2-focus"
          style={INPUT_STYLE}
        />
      </FilterField>

      {activeCount > 0 && (
        <button
          type="button"
          onClick={() => onChange(EMPTY_FILTERS)}
          className="v2-focus"
          style={{
            height: 32,
            padding: "0 12px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            color: "var(--text-secondary)",
            fontSize: 12,
            fontWeight: "var(--fw-medium)",
            cursor: "pointer",
          }}
        >
          Clear filters ({activeCount})
        </button>
      )}
    </section>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ ...LABEL, textTransform: "uppercase" }}>{label}</span>
      {children}
    </label>
  );
}

const INPUT_STYLE: CSSProperties = {
  height: 32,
  padding: "0 10px",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-input)",
  background: "var(--surface)",
  color: "var(--text-primary)",
  fontSize: 13,
  font: "inherit",
  minWidth: 140,
};

const SELECT_STYLE: CSSProperties = {
  ...INPUT_STYLE,
  minWidth: 180,
  cursor: "pointer",
};
