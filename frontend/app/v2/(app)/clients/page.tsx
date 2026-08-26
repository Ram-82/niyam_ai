"use client";

import { useState, type CSSProperties } from "react";
import {
  ArrowUpRightIcon,
  ChevronDownIcon,
  DownloadIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  UploadIcon,
  XIcon,
} from "@/components/v2/icons";
import { MiniAvatar, Monogram } from "@/components/v2/ui/Monogram";
import { StatusPill } from "@/components/v2/ui/StatusPill";
import { HealthTrack, toneForScore } from "@/components/v2/ui/HealthTrack";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { LoadingState } from "@/components/v2/ui/LoadingState";
import {
  clientsStats,
  describeDays,
  formatDate,
  formatPaise,
  formatPeriod,
  formatRelative,
  humanizeAction,
  initialsFrom,
  prettyReturnBadge,
  prettyReturnType,
  statusLabel,
  upcomingForClient,
  useClientActivity,
  useClientsData,
  type CalendarRow,
  type EnrichedClient,
} from "./useClientsData";

const LABEL: CSSProperties = {
  fontSize: "var(--fs-label)",
  lineHeight: "var(--lh-label)",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

const CARD: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-app-card)",
  boxShadow: "var(--shadow-card)",
};

export default function ClientsPage() {
  const { clients, calendar, loading, error, reload } = useClientsData();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = clients?.find((c) => c.id === selectedId) ?? clients?.[0] ?? null;
  const activeId = selected?.id ?? null;

  return (
    <div style={{ display: "flex", alignItems: "stretch", flex: 1, minWidth: 0 }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
        <PageHeader total={clients?.length ?? 0} loading={loading && !clients} />
        {error && (
          <div style={{ padding: "16px 32px 0" }}>
            <ErrorBanner message={`Could not load clients: ${error}`} onRetry={reload} />
          </div>
        )}
        <StatsStrip clients={clients} loading={loading && !clients} />
        <FilterRow />
        <TableSection
          clients={clients}
          loading={loading && !clients}
          activeId={activeId}
          onSelect={setSelectedId}
        />
      </div>
      <PreviewDrawer client={selected} calendar={calendar} loading={loading && !clients} />
    </div>
  );
}

/* --------------------------------- Header --------------------------------- */

function PageHeader({ total, loading }: { total: number; loading: boolean }) {
  return (
    <div style={{
      flex: "none", boxSizing: "border-box", height: 96,
      borderBottom: "1px solid var(--border)", padding: "24px 32px",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
          Firms · Venkatesh &amp; Co.
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h1 style={{
            margin: 0, fontSize: "var(--fs-h1)", lineHeight: "var(--lh-h1)",
            fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-h1)",
            color: "var(--text-primary)",
          }}>
            Clients
          </h1>
          <span
            style={{
              height: 24, boxSizing: "border-box", padding: "0 10px",
              display: "flex", alignItems: "center",
              border: "1px solid var(--border)", borderRadius: "var(--radius-chip)",
              background: "var(--surface)", fontSize: 12, fontWeight: "var(--fw-medium)",
              color: "var(--text-secondary)",
            }}
            className="tabular"
          >
            {loading ? "…" : total}
          </span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <SecondaryButton icon={<UploadIcon size={16} style={{ color: "var(--text-secondary)" }} />}>
          Import CSV
        </SecondaryButton>
        <SecondaryButton icon={<DownloadIcon size={16} style={{ color: "var(--text-secondary)" }} />}>
          Export
        </SecondaryButton>
        <button
          type="button"
          className="v2-btn-primary v2-focus"
          style={{
            height: 32, display: "flex", alignItems: "center", gap: 6,
            padding: "0 16px", border: 0, borderRadius: "var(--radius-input)",
            background: "var(--accent)", color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          <PlusIcon size={16} />
          Add client
        </button>
      </div>
    </div>
  );
}

function SecondaryButton({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      style={{
        height: 32, display: "flex", alignItems: "center", gap: 6,
        padding: "0 12px", border: "1px solid var(--border)",
        borderRadius: "var(--radius-input)", background: "var(--surface)",
        color: "var(--text-primary)", font: `500 13px/20px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {icon}
      {children}
    </button>
  );
}

/* --------------------------------- Stats --------------------------------- */

function StatsStrip({ clients, loading }: { clients: EnrichedClient[] | null; loading: boolean }) {
  const s = clientsStats(clients);
  const dash = loading || !clients;
  return (
    <div style={{ flex: "none", padding: "16px 32px 0" }}>
      <div style={{ ...CARD, height: 104, boxSizing: "border-box", display: "flex", alignItems: "stretch", overflow: "hidden" }}>
        <StatCell label="Total clients" value={dash ? "—" : String(s.total)} foot={<span style={{ color: "var(--text-muted)" }}>on your book</span>} />
        <Divider />
        <StatCell
          label="Active"
          value={dash ? "—" : String(s.active)}
          foot={<span style={{ color: "var(--text-muted)" }}>{dash ? "" : `${s.healthPct.compliant}% of book`}</span>}
        />
        <Divider />
        <StatCell
          label="At risk"
          value={dash ? "—" : String(s.at_risk)}
          foot={<span style={{ color: "var(--warning)" }}>{dash ? "" : "score < 60 or blocker"}</span>}
        />
        <Divider />
        <StatCell
          label="Overdue"
          value={dash ? "—" : String(s.overdue)}
          foot={<span style={{ color: "var(--danger)" }}>{dash ? "" : "unfiled past due"}</span>}
        />
        <Divider />
        <div style={{ flex: "none", boxSizing: "border-box", padding: "16px 24px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 8 }}>
          <div style={{ display: "flex", gap: 2, width: 240, height: 6 }}>
            <span style={{ width: `${s.healthPct.compliant}%`, background: "var(--success)", borderRadius: "var(--radius-pill)" }} />
            <span style={{ width: `${s.healthPct.onboarding}%`, background: "var(--accent)", borderRadius: "var(--radius-pill)" }} />
            <span style={{ width: `${s.healthPct.at_risk}%`, background: "var(--warning)", borderRadius: "var(--radius-pill)" }} />
            <span style={{ width: `${s.healthPct.overdue}%`, background: "var(--danger)", borderRadius: "var(--radius-pill)" }} />
          </div>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
            {dash ? "—" : `${s.total} client${s.total === 1 ? "" : "s"} by health`}
          </span>
        </div>
      </div>
    </div>
  );
}

function StatCell({ label, value, foot }: { label: string; value: string; foot: React.ReactNode }) {
  return (
    <div style={{ flex: 1, boxSizing: "border-box", padding: "16px 24px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 2 }}>
      <span style={LABEL}>{label}</span>
      <span className="tabular" style={{
        fontSize: "var(--fs-h1)", lineHeight: "var(--lh-h1)",
        fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-h1)",
        color: "var(--text-primary)",
      }}>
        {value}
      </span>
      <span style={{ fontSize: 12, lineHeight: "16px" }}>{foot}</span>
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, background: "var(--border)" }} />;
}

/* --------------------------------- Filter --------------------------------- */

function FilterRow() {
  return (
    <div style={{
      flex: "none", height: 56, boxSizing: "border-box", marginTop: 32,
      padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div className="v2-search-wrap" style={{
          width: 280, boxSizing: "border-box", height: 32,
          display: "flex", alignItems: "center", gap: 8, padding: "0 8px 0 10px",
          border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
          background: "var(--surface)",
        }}>
          <SearchIcon size={16} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search clients, GSTINs, PANs…"
            style={{
              flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent",
              font: `400 13px/20px var(--font-sans-v2)`, color: "var(--text-primary)",
            }}
          />
          <span style={{
            flex: "none", padding: "1px 5px",
            border: "1px solid var(--border)", borderRadius: "var(--radius-chip)",
            fontSize: 11, fontWeight: "var(--fw-medium)", color: "var(--text-muted)",
          }}>
            ⌘F
          </span>
        </div>
        <div style={{ width: 1, height: 20, background: "var(--border)" }} />
        <FilterChip>Status: All</FilterChip>
        <FilterChip>Plan: All</FilterChip>
        <FilterChip>State: All</FilterChip>
        <FilterChip>Owner: All</FilterChip>
        <FilterChip>Health: All</FilterChip>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flex: "none" }}>
        <IconButton aria-label="Customize columns" title="Customize columns">
          <SettingsIcon size={16} />
        </IconButton>
        <IconButton aria-label="Export current view" title="Export current view">
          <DownloadIcon size={16} />
        </IconButton>
        <div style={{ height: 32, display: "flex", alignItems: "stretch", border: "1px solid var(--border)", borderRadius: "var(--radius-input)", overflow: "hidden" }}>
          <button type="button" className="v2-focus-inset" style={{
            padding: "0 12px", border: 0, background: "var(--accent-soft)", color: "var(--accent)",
            font: `500 12px/16px var(--font-sans-v2)`, cursor: "pointer",
          }}>
            Table
          </button>
          <button type="button" className="v2-hover-tint v2-focus-inset" style={{
            padding: "0 12px", border: 0, borderLeft: "1px solid var(--border)",
            background: "transparent", color: "var(--text-secondary)",
            font: `500 12px/16px var(--font-sans-v2)`, cursor: "pointer",
          }}>
            Board
          </button>
        </div>
      </div>
    </div>
  );
}

function FilterChip({ children }: { children: React.ReactNode }) {
  return (
    <button type="button" className="v2-btn-secondary v2-focus" style={{
      height: 32, display: "flex", alignItems: "center", gap: 6,
      padding: "0 10px", border: "1px solid var(--border)",
      borderRadius: "var(--radius-input)", background: "var(--surface)",
      color: "var(--text-secondary)", font: `500 12px/16px var(--font-sans-v2)`,
      cursor: "pointer",
    }}>
      {children}
      <ChevronDownIcon size={12} />
    </button>
  );
}

function IconButton({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      {...rest}
      style={{
        width: 32, height: 32,
        display: "flex", alignItems: "center", justifyContent: "center",
        border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
        background: "var(--surface)", color: "var(--text-secondary)",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

/* --------------------------------- Table --------------------------------- */

function TableSection({
  clients, loading, activeId, onSelect,
}: {
  clients: EnrichedClient[] | null;
  loading: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div style={{ flex: 1, padding: "0 32px 32px", minHeight: 0 }}>
      <div style={{ ...CARD, overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            Loading clients…
          </div>
        ) : !clients || clients.length === 0 ? (
          <EmptyState message="No clients yet." hint="Add your first client to get started." />
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 40 }} />
              <col style={{ width: 280 }} />
              <col style={{ width: 170 }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 140 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 140 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 48 }} />
            </colgroup>
            <thead>
              <tr style={{ height: 48, borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: 0, textAlign: "center" }}>
                  <input type="checkbox" aria-label="Select all" style={{ width: 14, height: 14, accentColor: "var(--accent)", cursor: "pointer" }} />
                </th>
                <Th sortable>Client</Th>
                <Th>GSTIN</Th>
                <Th>Scheme</Th>
                <Th sortable active>Compliance health</Th>
                <Th>Last filed</Th>
                <Th>Next due</Th>
                <Th align="right">Amount at risk</Th>
                <Th>Owner</Th>
                <Th>Status</Th>
                <th style={{ padding: 0 }} />
              </tr>
            </thead>
            <tbody>
              {clients.map((c, i) => (
                <ClientRow
                  key={c.id}
                  c={c}
                  last={i === clients.length - 1}
                  active={c.id === activeId}
                  onSelect={() => onSelect(c.id)}
                />
              ))}
            </tbody>
          </table>
        )}
        {clients && clients.length > 0 && <Pager total={clients.length} shown={clients.length} />}
      </div>
    </div>
  );
}

function Th({
  children, align = "left", sortable, active,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  sortable?: boolean;
  active?: boolean;
}) {
  const base: CSSProperties = {
    padding: "0 12px", textAlign: align,
    font: `500 11px/16px var(--font-sans-v2)`,
    letterSpacing: "var(--tr-label)", textTransform: "uppercase",
    color: active ? "var(--text-primary)" : "var(--text-muted)",
    boxShadow: active ? "inset 0 -2px 0 var(--accent)" : undefined,
  };
  return (
    <th style={base}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: sortable ? "pointer" : undefined }}>
        {children}
        {sortable && <ChevronDownIcon size={12} style={{ opacity: active ? 1 : 0.5 }} />}
      </span>
    </th>
  );
}

function ClientRow({ c, last, active, onSelect }: {
  c: EnrichedClient; last: boolean; active: boolean; onSelect: () => void;
}) {
  const rowStyle: CSSProperties = active
    ? {
        height: 56,
        borderBottom: last ? undefined : "1px solid var(--border)",
        background: "var(--row-hover-accent)",
        boxShadow: "inset 2px 0 0 var(--accent)",
        cursor: "pointer",
      }
    : {
        height: 56,
        borderBottom: last ? undefined : "1px solid var(--border)",
        cursor: "pointer",
      };

  const scoreTone = c.score !== null ? toneForScore(c.score) : "danger";
  const scoreColor =
    scoreTone === "success" ? "var(--success)" :
    scoreTone === "warning" ? "var(--warning)" : "var(--danger)";
  const amount = formatPaise(c.amount_at_risk_paise);
  const status = statusLabel(c.status);

  const nextDueColor =
    c.next_due_days === null
      ? "var(--text-muted)"
      : c.next_due_days < 0
      ? "var(--danger)"
      : c.next_due_days <= 3
      ? "var(--warning)"
      : "var(--text-primary)";
  const nextDueDate = c.next_due_days === null
    ? "—"
    : formatDate(new Date(Date.now() + c.next_due_days * 86400000).toISOString());

  return (
    <tr
      className={active ? "" : "v2-row"}
      style={rowStyle}
      onClick={onSelect}
    >
      <td style={{ padding: 0, textAlign: "center" }} onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" aria-label={`Select ${c.trade_name}`} style={{ width: 14, height: 14, accentColor: "var(--accent)", cursor: "pointer" }} />
      </td>
      <td style={{ padding: "0 12px 0 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Monogram initials={initialsFrom(c.trade_name)} />
          <span style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
            <span style={{
              fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)",
              color: "var(--text-primary)",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {c.trade_name}
            </span>
            <span style={{
              fontSize: 12, lineHeight: "16px", color: "var(--text-muted)",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {c.total_returns_tracked > 0
                ? `${c.total_returns_tracked} returns tracked · ${c.language.toUpperCase()}`
                : `No returns yet · ${c.language.toUpperCase()}`}
            </span>
          </span>
        </div>
      </td>
      <td style={{ padding: "0 12px" }}>
        {c.gstin ? (
          <span style={{ display: "flex", flexDirection: "column" }}>
            <span className="mono" style={{ color: "var(--text-secondary)" }}>{c.gstin}</span>
            <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{c.gstin.slice(0, 2)}</span>
          </span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>—</span>
        )}
      </td>
      <td style={{ padding: "0 12px" }}>
        {c.scheme ? (
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-primary)", textTransform: "capitalize" }}>
            {c.scheme}
          </span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>—</span>
        )}
      </td>
      <td style={{ padding: "0 12px" }}>
        {c.score !== null ? (
          <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <HealthTrack score={c.score} />
              <span className="tabular" style={{ fontSize: 13, fontWeight: "var(--fw-medium)", color: scoreColor }}>{c.score}</span>
            </span>
            <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>
              {c.blockers_count > 0 ? `${c.blockers_count} blocker${c.blockers_count === 1 ? "" : "s"}` : "no blockers"}
            </span>
          </span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>—</span>
        )}
      </td>
      <td style={{ padding: "0 12px" }}>
        <span className="tabular" style={{
          fontSize: 13, lineHeight: "18px",
          color: c.last_filed_at ? "var(--text-primary)" : "var(--text-muted)",
        }}>
          {formatDate(c.last_filed_at)}
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span className="tabular" style={{ fontSize: 13, lineHeight: "18px", color: nextDueColor }}>
            {nextDueDate}
          </span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>
            {c.next_due_label ?? "no upcoming return"}
          </span>
        </span>
      </td>
      <td className="tabular" style={{
        padding: "0 12px", textAlign: "right",
        fontSize: 13, fontWeight: amount.weight, color: amount.color,
      }}>
        {amount.text}
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <MiniAvatar initials="—" />
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Unassigned</span>
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <StatusPill tone={status.tone}>{status.label}</StatusPill>
      </td>
      <td style={{ padding: "0 8px", textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
        <button
          type="button" aria-label="Row actions"
          className="v2-row-actions v2-focus"
          style={{
            width: 28, height: 28,
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-chip)",
            background: "transparent", color: "var(--text-secondary)",
            cursor: "pointer",
          }}
        >
          <MoreHorizontalIcon size={16} />
        </button>
      </td>
    </tr>
  );
}

function Pager({ total, shown }: { total: number; shown: number }) {
  return (
    <div style={{
      height: 56, boxSizing: "border-box",
      borderTop: "1px solid var(--border)", padding: "0 16px",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
    }}>
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }} className="tabular">
        1–{shown} of {total} clients
      </span>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Pagination coming next</span>
      <span />
    </div>
  );
}

/* --------------------------------- Drawer --------------------------------- */

function PreviewDrawer({
  client, calendar, loading,
}: {
  client: EnrichedClient | null;
  calendar: import("./useClientsData").CalendarResponse | null;
  loading: boolean;
}) {
  const { items: activity, loading: activityLoading } = useClientActivity(client?.id ?? null);

  if (loading) {
    return (
      <aside style={{
        width: 400, flex: "none", boxSizing: "border-box",
        background: "var(--surface)", borderLeft: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <LoadingState />
      </aside>
    );
  }

  if (!client) {
    return (
      <aside style={{
        width: 400, flex: "none", boxSizing: "border-box",
        background: "var(--surface)", borderLeft: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "center",
        color: "var(--text-muted)", fontSize: 13, padding: 20, textAlign: "center",
      }}>
        Select a client to see details.
      </aside>
    );
  }

  const status = statusLabel(client.status);
  const upcoming = upcomingForClient(calendar, client.id);

  return (
    <aside style={{
      width: 400, flex: "none", boxSizing: "border-box",
      background: "var(--surface)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column", minHeight: 0,
    }}>
      <div style={{
        height: 72, flex: "none", boxSizing: "border-box",
        padding: "16px 20px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <span style={{
          width: 40, height: 40, flex: "none", borderRadius: 8,
          background: "var(--accent-soft)", color: "var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: "var(--fw-semi)",
        }}>
          {initialsFrom(client.trade_name)}
        </span>
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{
            fontSize: 18, lineHeight: "22px", fontWeight: "var(--fw-semi)",
            color: "var(--text-primary)",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {client.trade_name}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <StatusPill tone={status.tone}>{status.label}</StatusPill>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
              {client.language.toUpperCase()}
            </span>
          </span>
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        <div style={{
          padding: "16px 20px", background: "var(--bg)",
          display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 12px",
          fontSize: 12, lineHeight: "16px",
        }}>
          <MetaKey>GSTIN</MetaKey><MetaVal mono>{client.gstin ?? "—"}</MetaVal>
          <MetaKey>Scheme</MetaKey><MetaVal>{client.scheme ? cap(client.scheme) : "—"}</MetaVal>
          <MetaKey>Returns tracked</MetaKey><MetaVal>{client.total_returns_tracked}</MetaVal>
          <MetaKey>Filed to date</MetaKey><MetaVal>{client.filed_this_month}</MetaVal>
          <MetaKey>WhatsApp</MetaKey><MetaVal>{client.whatsapp_number ?? "—"}</MetaVal>
        </div>

        <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
          <ComplianceCard client={client} />
          <UpcomingCard rows={upcoming} />
          <ActivityCard items={activity} loading={activityLoading} />
          <KeyContactCard client={client} />
        </div>
      </div>

      <div style={{
        height: 120, flex: "none", boxSizing: "border-box",
        borderTop: "1px solid var(--border)", padding: "16px 20px",
        display: "flex", flexDirection: "column", gap: 8,
      }}>
        <button type="button" className="v2-btn-primary v2-focus" style={{
          flex: "none", height: 40,
          display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          border: 0, borderRadius: "var(--radius-input)",
          background: "var(--accent)", color: "var(--on-accent)",
          font: `500 14px/20px var(--font-sans-v2)`, cursor: "pointer",
        }}>
          Open full profile
          <ArrowUpRightIcon size={14} />
        </button>
        <div style={{ flex: "none", height: 32, display: "flex", alignItems: "center", gap: 8 }}>
          <DrawerGhostBtn>Add note</DrawerGhostBtn>
          <DrawerGhostBtn>Add filing task</DrawerGhostBtn>
        </div>
      </div>
    </aside>
  );
}

function cap(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

function MetaKey({ children }: { children: React.ReactNode }) {
  return <span style={{ color: "var(--text-muted)" }}>{children}</span>;
}

function MetaVal({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <span
      className={mono ? "mono" : "tabular"}
      style={{ textAlign: "right", color: "var(--text-primary)", fontSize: mono ? 13 : undefined }}
    >
      {children}
    </span>
  );
}

function DrawerGhostBtn({ children }: { children: React.ReactNode }) {
  return (
    <button type="button" className="v2-btn-secondary v2-focus" style={{
      flex: 1, height: 32, border: "1px solid var(--border)",
      borderRadius: "var(--radius-input)", background: "transparent",
      font: `500 13px/20px var(--font-sans-v2)`,
      color: "var(--text-primary)", cursor: "pointer",
    }}>
      {children}
    </button>
  );
}

function ComplianceCard({ client }: { client: EnrichedClient }) {
  const score = client.score;
  const scoreTone = score !== null ? toneForScore(score) : null;
  const scoreColor =
    scoreTone === "success" ? "var(--success)" :
    scoreTone === "warning" ? "var(--warning)" :
    scoreTone === "danger" ? "var(--danger)" : "var(--text-muted)";

  return (
    <div style={{
      boxSizing: "border-box", padding: 16,
      border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ height: 24, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          Compliance health
        </span>
        <span className="tabular" style={{ fontSize: 14, fontWeight: "var(--fw-semi)", color: scoreColor }}>
          {score !== null ? `${score}/100` : "—"}
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        <KpiMini
          label="Filed to date"
          value={client.filed_this_month}
          foot={<span style={{ color: "var(--text-muted)" }}>tracked</span>}
        />
        <KpiMini
          label="Blockers"
          value={client.blockers_count}
          foot={<span style={{ color: client.blockers_count > 0 ? "var(--warning)" : "var(--text-muted)" }}>
            {client.blockers_count > 0 ? "open" : "clear"}
          </span>}
        />
        <KpiMini
          label="Next due"
          value={<span>{describeDays(client.next_due_days)}</span>}
          foot={<span style={{ color: "var(--text-muted)" }}>
            {client.next_due_label ?? "—"}
          </span>}
        />
      </div>
    </div>
  );
}

function KpiMini({ label, value, foot }: { label: string; value: React.ReactNode; foot: React.ReactNode }) {
  return (
    <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</span>
      <span className="tabular" style={{ fontSize: 14, fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>{value}</span>
      <span style={{ fontSize: 11 }}>{foot}</span>
    </span>
  );
}

function UpcomingCard({ rows }: { rows: CalendarRow[] }) {
  return (
    <div style={{
      boxSizing: "border-box", border: "1px solid var(--border)",
      borderRadius: "var(--radius-app-card)", overflow: "hidden",
    }}>
      <div style={{ padding: "16px 16px 12px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          Upcoming
        </span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <div style={{ padding: "0 16px 16px" }}>
          <EmptyState variant="inline" message="No unfiled returns on the horizon." />
        </div>
      ) : (
        rows.map((r) => {
          const overdue = r.days_out < 0;
          const dueSoon = r.days_out >= 0 && r.days_out <= 7;
          const tone = overdue ? "danger" : dueSoon ? "warning" : null;
          return (
            <div key={`${r.gstin_profile_id}-${r.period}-${r.return_type}`} style={{
              height: 48, boxSizing: "border-box",
              padding: "0 16px", borderTop: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{
                flex: "none", height: 20, padding: "0 6px",
                display: "flex", alignItems: "center",
                border: "1px solid var(--border)", borderRadius: 4,
                color: "var(--text-secondary)",
                fontSize: 10, fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-label)",
              }}>
                {prettyReturnBadge(r.return_type)}
              </span>
              <span style={{
                flex: 1, minWidth: 0, fontSize: 13, color: "var(--text-primary)",
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>
                {formatPeriod(r.period)}
              </span>
              {tone ? (
                <span style={{
                  flex: "none", padding: "2px 8px", borderRadius: "var(--radius-chip)",
                  background: tone === "danger" ? "var(--danger-soft)" : "var(--warning-soft)",
                  color: tone === "danger" ? "var(--danger)" : "var(--warning)",
                  fontSize: 11, lineHeight: "16px", fontWeight: "var(--fw-medium)",
                }}>
                  {formatDate(r.due_date)} · {describeDays(r.days_out)}
                </span>
              ) : (
                <span className="tabular" style={{ flex: "none", fontSize: 11, color: "var(--text-muted)" }}>
                  {formatDate(r.due_date)} · {describeDays(r.days_out)}
                </span>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

function ActivityCard({ items, loading }: { items: import("./useClientsData").AuditRow[] | null; loading: boolean }) {
  return (
    <div style={{
      boxSizing: "border-box", padding: 16,
      border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
        Recent activity
      </span>
      {loading ? (
        <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Loading activity…</span>
      ) : !items || items.length === 0 ? (
        <EmptyState variant="inline" message="No client-level audit events yet." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, borderLeft: "1px solid var(--border)", paddingLeft: 16 }}>
          {items.map((a) => {
            const success = a.action.includes(".created") || a.action.includes(".approved") || a.action.includes(".filed") || a.action.includes(".resolved");
            return (
              <div key={a.id} style={{ position: "relative", display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{
                  position: "absolute", left: -20, top: 5,
                  width: 8, height: 8, borderRadius: "var(--radius-pill)",
                  background: success ? "var(--success)" : "var(--border-strong)",
                  boxShadow: "0 0 0 3px var(--surface)",
                }} />
                <span style={{ fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>
                  {humanizeAction(a.action)}
                  {a.user_email && <> · {a.user_email}</>}
                </span>
                <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>
                  {formatRelative(a.at)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function KeyContactCard({ client }: { client: EnrichedClient }) {
  return (
    <div style={{
      boxSizing: "border-box", padding: 16,
      border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
        Key contact
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        {client.whatsapp_number ? (
          <ContactChip tone="success">
            <MessageSvg />
            {client.whatsapp_number}
          </ContactChip>
        ) : (
          <ContactChip>
            <MessageSvg />
            No WhatsApp
          </ContactChip>
        )}
        <ContactChip>Language: {client.language.toUpperCase()}</ContactChip>
      </div>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
        Contact roles + emails will surface here once client profile capture ships.
      </span>
    </div>
  );
}

function ContactChip({ children, tone }: { children: React.ReactNode; tone?: "success" }) {
  return (
    <span style={{
      height: 24, boxSizing: "border-box",
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "0 8px", border: "1px solid var(--border)",
      borderRadius: "var(--radius-chip)",
      fontSize: 11,
      color: tone === "success" ? "var(--success)" : "var(--text-secondary)",
    }}>
      {children}
    </span>
  );
}

function MessageSvg() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.5 8.5 0 0 1-12.5 7.5L3 21l2-5.5A8.5 8.5 0 1 1 21 11.5" />
    </svg>
  );
}
