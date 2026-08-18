"use client";

import { useState, type CSSProperties } from "react";
import Link from "next/link";
import {
  AlertTriangleIcon,
  ArrowUpDownIcon,
  ArrowUpIcon,
  CalendarIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  DownloadIcon,
  FilterIcon,
  MessageSquareIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
  UploadIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { MiniAvatar, Monogram } from "@/components/v2/ui/Monogram";
import { StatusPill, type StatusTone } from "@/components/v2/ui/StatusPill";
import {
  buildMonthGrid,
  computeDistributionPct,
  formatDueDate,
  formatDueStatus,
  formatPaise,
  formatRelative,
  initialsFrom,
  pickAtRiskRows,
  useDashboardData,
  type CalendarCell,
  type CommandCenterRow,
  type FirmHealthSummary,
  type RecentActivityItem,
} from "./useDashboardData";

/* --------------------------------- Styles --------------------------------- */

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

const SECTION_TITLE: CSSProperties = {
  margin: 0,
  fontSize: "var(--fs-h2)",
  lineHeight: "var(--lh-h2)",
  fontWeight: "var(--fw-semi)",
  color: "var(--text-primary)",
};

const eventToneStyle: Record<CalendarCell["events"][number]["tone"], CSSProperties> = {
  success: { background: "var(--success-soft)", color: "var(--success)" },
  warning: { background: "var(--warning-soft)", color: "var(--warning)" },
  danger: { background: "var(--danger-soft)", color: "var(--danger)" },
  neutral: { background: "var(--row-hover)", color: "var(--text-secondary)" },
};

/* --------------------------------- Page --------------------------------- */

export default function DashboardPage() {
  const { data, loading, error, reload } = useDashboardData();
  const cells = buildMonthGrid(data.calendar);
  const atRiskPool = pickAtRiskRows(data.commandCenter, Number.POSITIVE_INFINITY);
  const monthLabel = data.calendar
    ? new Date(data.calendar.today).toLocaleDateString("en-IN", { month: "long", year: "numeric" })
    : "";

  return (
    <div
      style={{
        padding: 32,
        display: "flex",
        flexDirection: "column",
        gap: 24,
        maxWidth: 1504,
        width: "100%",
      }}
    >
      {error && <ErrorBanner message={`Some dashboard data failed to load: ${error}`} onRetry={reload} />}

      {/* --- Page header --- */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1
            style={{
              margin: 0,
              fontSize: "var(--fs-display)",
              lineHeight: "var(--lh-display)",
              fontWeight: "var(--fw-semi)",
              letterSpacing: "var(--tr-display)",
              color: "var(--text-primary)",
            }}
          >
            Compliance Overview
          </h1>
          <p style={{ margin: 0, fontSize: "var(--fs-body)", lineHeight: "var(--lh-body)", color: "var(--text-secondary)" }}>
            {data.health ? `${data.health.active_clients_count} active clients` : loading ? "Loading firm data…" : "No data yet"}
            {data.commandCenter && ` · Period ${formatPeriod(data.commandCenter.period)}`}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            className="v2-btn-secondary v2-focus"
            style={{
              display: "flex", alignItems: "center", gap: 8, height: 36, padding: "0 12px",
              border: "1px solid var(--border-strong)", borderRadius: "var(--radius-input)",
              background: "var(--surface)", color: "var(--text-primary)",
              font: `500 var(--fs-body)/var(--lh-body) var(--font-sans-v2)`, cursor: "pointer",
            }}
          >
            <CalendarIcon size={16} style={{ color: "var(--text-secondary)" }} />
            This month
            <ChevronDownIcon size={16} style={{ color: "var(--text-muted)" }} />
          </button>
          <button
            type="button"
            className="v2-btn-primary v2-focus"
            style={{
              display: "flex", alignItems: "center", gap: 6, height: 36, padding: "0 14px",
              border: 0, borderRadius: "var(--radius-input)",
              background: "var(--accent)", color: "var(--on-accent)",
              font: `500 var(--fs-body)/var(--lh-body) var(--font-sans-v2)`, cursor: "pointer",
            }}
          >
            <PlusIcon size={16} />
            New Filing
          </button>
        </div>
      </div>

      {/* --- Row 1: health card + 4 KPIs --- */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 24 }}>
        <HealthCard health={data.health} loading={loading} />
        <div style={{ gridColumn: "span 7", display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 24 }}>
          <KpiCard
            label="Upcoming deadlines"
            value={deriveUpcomingCount(data.calendar)}
            sub="Next 7 days"
            indicator={<ClockIcon size={16} style={{ color: "var(--text-muted)" }} />}
            loading={loading}
          />
          <KpiCard
            label="Pending filings"
            value={data.commandCenter?.summary.unfiled_count ?? null}
            sub="Awaiting client docs or approval"
            indicator={<Dot color="var(--warning)" />}
            loading={loading}
          />
          <KpiCard
            label="At-risk clients"
            value={data.health?.distribution.overdue_blocked ?? null}
            sub="Overdue or high-risk"
            indicator={<Dot color="var(--danger)" />}
            loading={loading}
          />
          <KpiCard
            label="Filed this month"
            value={data.commandCenter?.summary.filed_count ?? null}
            sub={deriveFiledSub(data.commandCenter)}
            indicator={<Dot color="var(--success)" />}
            loading={loading}
          />
        </div>
      </div>

      {/* --- Row 2: calendar + activity --- */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 24, alignItems: "start" }}>
        <CalendarCard cells={cells} monthLabel={monthLabel} loading={loading} />
        <ActivityCard items={data.activity} loading={loading} />
      </div>

      {/* --- Row 3: at-risk table --- */}
      <AtRiskSection pool={atRiskPool} loading={loading} totalHigh={data.commandCenter?.summary.high_risk_count ?? 0} />
    </div>
  );
}

/* --------------------------------- Error banner --------------------------------- */

/* --------------------------------- Row 1 --------------------------------- */

function HealthCard({ health, loading }: { health: FirmHealthSummary | null; loading: boolean }) {
  const score = health?.score ?? null;
  const prev = health?.prev_score ?? null;
  const delta = score !== null && prev !== null ? score - prev : null;
  const { healthyPct, dueSoonPct, overduePct } = health
    ? computeDistributionPct(health.distribution)
    : { healthyPct: 0, dueSoonPct: 0, overduePct: 0 };

  const band =
    score === null
      ? { label: "No data", bg: "var(--row-hover)", fg: "var(--text-secondary)" }
      : score >= 75
      ? { label: "Healthy", bg: "var(--success-soft)", fg: "var(--success)" }
      : score >= 60
      ? { label: "At risk", bg: "var(--warning-soft)", fg: "var(--warning)" }
      : { label: "Critical", bg: "var(--danger-soft)", fg: "var(--danger)" };

  return (
    <section
      style={{
        ...CARD,
        gridColumn: "span 5",
        boxSizing: "border-box",
        height: 200,
        padding: "20px 24px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={LABEL}>Firm compliance health</span>
        {delta !== null && delta !== 0 && (
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              fontSize: 12,
              lineHeight: "16px",
              fontWeight: 500,
              color: delta > 0 ? "var(--success)" : "var(--danger)",
            }}
          >
            <ArrowUpIcon size={12} style={delta < 0 ? { transform: "rotate(180deg)" } : undefined} />
            {delta > 0 ? "+" : ""}
            {delta} vs last month
          </span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 12 }}>
        <span
          style={{
            fontSize: "var(--fs-display)",
            lineHeight: "var(--lh-display)",
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-display)",
            color: "var(--text-primary)",
          }}
          className="tabular"
        >
          {loading && score === null ? "—" : score !== null ? score : "—"}
        </span>
        <span style={{ fontSize: 18, lineHeight: "28px", fontWeight: "var(--fw-semi)", color: "var(--text-muted)" }}>/100</span>
        <span
          style={{
            marginLeft: 8,
            padding: "2px 8px",
            borderRadius: "var(--radius-chip)",
            background: band.bg,
            color: band.fg,
            fontSize: 12,
            lineHeight: "16px",
            fontWeight: 500,
          }}
        >
          {band.label}
        </span>
      </div>
      <div style={{ display: "flex", gap: 3, height: 8, marginTop: "auto" }}>
        <span
          title={health ? `Healthy · ${health.distribution.healthy} clients` : ""}
          style={{ width: `${healthyPct}%`, borderRadius: "var(--radius-pill)", background: "var(--success)" }}
        />
        <span
          title={health ? `Due within 7 days · ${health.distribution.due_soon} clients` : ""}
          style={{ width: `${dueSoonPct}%`, borderRadius: "var(--radius-pill)", background: "var(--warning)" }}
        />
        <span
          title={health ? `Overdue or blocked · ${health.distribution.overdue_blocked} clients` : ""}
          style={{ width: `${overduePct}%`, borderRadius: "var(--radius-pill)", background: "var(--danger)" }}
        />
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: 12,
          fontSize: 12,
          lineHeight: "16px",
          color: "var(--text-muted)",
        }}
      >
        <span>
          {health ? `Across ${health.active_clients_count} active clients · Updated ${formatRelative(health.last_computed_at)}` : "Awaiting first snapshot"}
        </span>
        <span style={{ display: "flex", gap: 12 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Dot color="var(--success)" size={6} />{healthyPct}%</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Dot color="var(--warning)" size={6} />{dueSoonPct}%</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Dot color="var(--danger)" size={6} />{overduePct}%</span>
        </span>
      </div>
    </section>
  );
}

function KpiCard({
  label,
  value,
  sub,
  indicator,
  loading,
}: {
  label: string;
  value: number | null;
  sub: string;
  indicator: React.ReactNode;
  loading: boolean;
}) {
  return (
    <div
      className="v2-kpi"
      style={{
        ...CARD,
        boxSizing: "border-box",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        color: "inherit",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <span style={LABEL}>{label}</span>
        {indicator}
      </div>
      <span
        className="tabular"
        style={{
          fontSize: "var(--fs-h1)",
          lineHeight: "var(--lh-h1)",
          fontWeight: "var(--fw-semi)",
          letterSpacing: "var(--tr-h1)",
          color: "var(--text-primary)",
        }}
      >
        {value === null ? (loading ? "…" : "—") : value}
      </span>
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>{sub}</span>
    </div>
  );
}

function Dot({ color, size = 8 }: { color: string; size?: number }) {
  return <span style={{ width: size, height: size, borderRadius: "var(--radius-pill)", background: color, display: "inline-block" }} />;
}

/* --------------------------------- Row 2 --------------------------------- */

function CalendarCard({ cells, monthLabel, loading }: { cells: CalendarCell[]; monthLabel: string; loading: boolean }) {
  return (
    <section style={{ ...CARD, gridColumn: "span 8", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "16px 24px", borderBottom: "1px solid var(--border)" }}>
        <h2 style={SECTION_TITLE}>Statutory Calendar</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            className="v2-hover-tint v2-focus"
            style={{
              display: "flex", alignItems: "center", gap: 6, height: 28, padding: "0 10px",
              border: "1px solid var(--border)", borderRadius: "var(--radius-chip)",
              background: "transparent", color: "var(--text-secondary)",
              font: `500 var(--fs-label)/var(--lh-label) var(--font-sans-v2)`,
              letterSpacing: "var(--tr-label)", textTransform: "uppercase", cursor: "pointer",
            }}
          >
            All returns
            <ChevronDownIcon size={12} />
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button type="button" aria-label="Previous month" className="v2-hover-tint v2-focus"
              style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--border)", borderRadius: "var(--radius-chip)", background: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
              <ChevronLeftIcon size={14} />
            </button>
            <span style={{ minWidth: 104, textAlign: "center", fontSize: 14, fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>{monthLabel || "—"}</span>
            <button type="button" aria-label="Next month" className="v2-hover-tint v2-focus"
              style={{ width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--border)", borderRadius: "var(--radius-chip)", background: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}>
              <ChevronRightIcon size={14} />
            </button>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", padding: "0 24px", borderBottom: "1px solid var(--border)" }}>
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <span key={d} style={{ padding: "8px 4px", ...LABEL }}>{d}</span>
        ))}
      </div>

      {cells.length === 0 && loading ? (
        <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>Loading calendar…</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 1, background: "var(--border)", borderTop: "1px solid var(--border)" }}>
          {cells.map((cell, i) => (
            <CalendarCellView key={i} cell={cell} />
          ))}
        </div>
      )}
    </section>
  );
}

function CalendarCellView({ cell }: { cell: CalendarCell }) {
  const bg = cell.weekend ? "var(--bg)" : "var(--surface)";
  const dayColor = cell.today
    ? "var(--accent)"
    : cell.muted
    ? "var(--text-muted)"
    : cell.weekend
    ? "var(--text-muted)"
    : "var(--text-secondary)";

  if (cell.today) {
    return (
      <div
        style={{
          minHeight: 88,
          padding: 6,
          background: "var(--surface)",
          display: "flex",
          flexDirection: "column",
          gap: 4,
          border: "2px solid var(--accent)",
          borderRadius: 6,
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: "var(--fw-semi)", color: "var(--accent)" }}>
          {cell.day}{" "}
          <span style={{ fontSize: 11, fontWeight: "var(--fw-medium)", letterSpacing: "var(--tr-label)", textTransform: "uppercase" }}>Today</span>
        </span>
        {cell.events.map((e, i) => <EventPill key={i} tone={e.tone} tip={e.tip}>{e.label}</EventPill>)}
      </div>
    );
  }

  return (
    <div style={{ minHeight: 88, padding: 8, background: bg, display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: dayColor }}>{cell.day}</span>
      {cell.events.map((e, i) => <EventPill key={i} tone={e.tone} tip={e.tip}>{e.label}</EventPill>)}
      {cell.more != null && (
        <span style={{ fontSize: 11, lineHeight: "16px", color: "var(--text-muted)", paddingLeft: 6, cursor: "default" }}>
          +{cell.more} more
        </span>
      )}
    </div>
  );
}

function EventPill({ tone, tip, children }: { tone: CalendarCell["events"][number]["tone"]; tip: string; children: React.ReactNode }) {
  return (
    <span
      title={tip}
      style={{
        padding: "2px 6px",
        borderRadius: 4,
        fontSize: 11,
        lineHeight: "16px",
        fontWeight: "var(--fw-medium)",
        cursor: "default",
        ...eventToneStyle[tone],
      }}
    >
      {children}
    </span>
  );
}

/* --------------------------------- Activity --------------------------------- */

function ActivityCard({ items, loading }: { items: RecentActivityItem[] | null; loading: boolean }) {
  return (
    <section style={{ ...CARD, gridColumn: "span 4", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 24px", borderBottom: "1px solid var(--border)" }}>
        <h2 style={SECTION_TITLE}>Recent Activity</h2>
        <Link
          href="/v2/audit-log"
          className="v2-focus"
          style={{ fontSize: 12, lineHeight: "16px", fontWeight: "var(--fw-medium)", color: "var(--text-secondary)", textDecoration: "none" }}
        >
          View all →
        </Link>
      </div>
      <div style={{ position: "relative", padding: "20px 24px 8px" }}>
        {items === null && loading && (
          <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "0 4px 12px" }}>Loading activity…</div>
        )}
        {items !== null && items.length === 0 && (
          <div style={{ padding: "0 4px 12px" }}><EmptyState variant="inline" message="No recent activity yet." /></div>
        )}
        {items && items.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20, borderLeft: "1px solid var(--border)", paddingLeft: 20 }}>
            {items.map((it) => (
              <div key={it.id} style={{ position: "relative", display: "flex", gap: 12 }}>
                <span
                  style={{
                    position: "absolute", left: -25, top: 5, width: 9, height: 9,
                    borderRadius: "var(--radius-pill)",
                    background:
                      it.tone === "success" ? "var(--success)" :
                      it.tone === "danger" ? "var(--danger)" : "var(--border-strong)",
                    boxShadow: "0 0 0 3px var(--surface)",
                  }}
                />
                <span style={{ flex: "none", marginTop: 2 }}>{iconFor(it.icon, it.tone)}</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span style={{ fontSize: 14, lineHeight: "20px", color: "var(--text-primary)" }}>
                    <strong style={{ fontWeight: 500 }}>{it.title}</strong>
                    {it.subtitle && <> · {it.subtitle}</>}
                  </span>
                  <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
                    {formatRelative(it.at)}{it.actor_email && ` · by ${it.actor_email}`}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
        <div
          style={{
            position: "absolute", left: 0, right: 0, bottom: 0, height: 56,
            background: "linear-gradient(to bottom, transparent, var(--surface))",
            pointerEvents: "none",
          }}
        />
      </div>
    </section>
  );
}

function iconFor(icon: RecentActivityItem["icon"], tone: RecentActivityItem["tone"]) {
  const color =
    tone === "success" ? "var(--success)" : tone === "danger" ? "var(--danger)" : "var(--text-secondary)";
  const props = { size: 16 as const, style: { color } };
  switch (icon) {
    case "check": return <CheckCircleIcon {...props} />;
    case "alert": return <AlertTriangleIcon {...props} />;
    case "upload": return <UploadIcon {...props} />;
    case "settings": return <ClockIcon {...props} />;
    case "message":
    default: return <MessageSquareIcon {...props} />;
  }
}

/* --------------------------------- Row 3 --------------------------------- */

const AT_RISK_PAGE_SIZE = 6;

function AtRiskSection({ pool, loading, totalHigh }: { pool: CommandCenterRow[]; loading: boolean; totalHigh: number }) {
  const [visibleCount, setVisibleCount] = useState(AT_RISK_PAGE_SIZE);
  const rows = pool.slice(0, visibleCount);
  const hasMore = pool.length > rows.length;
  return (
    <section style={{ ...CARD, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "16px 24px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <h2 style={SECTION_TITLE}>At-Risk Clients</h2>
          <span style={{ padding: "2px 8px", borderRadius: "var(--radius-pill)", background: "var(--danger-soft)", color: "var(--danger)", fontSize: 12, lineHeight: "16px", fontWeight: "var(--fw-semi)" }}>
            {totalHigh}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            className="v2-search-wrap"
            style={{ display: "flex", alignItems: "center", gap: 8, width: 240, height: 32, padding: "0 10px", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-input)", background: "var(--surface)" }}
          >
            <SearchIcon size={16} style={{ color: "var(--text-muted)" }} />
            <input
              type="text"
              placeholder="Search clients"
              style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent", font: `400 13px/20px var(--font-sans-v2)`, color: "var(--text-primary)" }}
            />
          </div>
          <ToolbarButton icon={<FilterIcon size={16} />} label="Filter" />
          <ToolbarButton icon={<DownloadIcon size={16} />} label="Export" />
        </div>
      </div>

      {rows.length === 0 && loading ? (
        <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>Loading at-risk clients…</div>
      ) : rows.length === 0 ? (
        <EmptyState message="No at-risk clients." hint="Everything on track." />
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: 300 }} />
            <col style={{ width: 190 }} />
            <col style={{ width: 130 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 180 }} />
            <col style={{ width: 150 }} />
            <col style={{ width: 200 }} />
            <col style={{ width: 80 }} />
          </colgroup>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <Th sortable>Client</Th>
              <Th px={12}>GSTIN</Th>
              <Th px={12} sortable>Return</Th>
              <Th px={12} sortable active>Due date</Th>
              <Th px={12} sortable align="right">Amount at risk</Th>
              <Th px={12}>Status</Th>
              <Th px={12}>Owner</Th>
              <Th align="right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => <AtRiskRow key={`${r.gstin_profile_id}-${r.return_type}`} r={r} />)}
          </tbody>
        </table>
      )}

      <div style={{ padding: "12px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        {hasMore ? (
          <button
            type="button"
            onClick={() => setVisibleCount((n) => n + AT_RISK_PAGE_SIZE)}
            className="v2-focus"
            style={{
              padding: "6px 12px",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-input)",
              background: "var(--surface)",
              color: "var(--text-primary)",
              fontSize: 13,
              fontWeight: "var(--fw-medium)",
              cursor: "pointer",
            }}
          >
            Load more
          </button>
        ) : rows.length > AT_RISK_PAGE_SIZE ? (
          <button
            type="button"
            onClick={() => setVisibleCount(AT_RISK_PAGE_SIZE)}
            className="v2-focus"
            style={{
              padding: "6px 12px",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-input)",
              background: "var(--surface)",
              color: "var(--text-secondary)",
              fontSize: 13,
              fontWeight: "var(--fw-medium)",
              cursor: "pointer",
            }}
          >
            Show less
          </button>
        ) : (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>End of list.</span>
        )}
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Showing {rows.length} of {pool.length} at-risk filings · sorted by score
          {totalHigh > pool.length ? ` · ${totalHigh - pool.length} more scored high-risk` : ""}
        </span>
      </div>
    </section>
  );
}

function Th({ children, px = 24, align = "left", sortable, active }: { children: React.ReactNode; px?: number; align?: "left" | "right"; sortable?: boolean; active?: boolean }) {
  const base: CSSProperties = {
    padding: `10px ${px}px`,
    textAlign: align,
    fontSize: "var(--fs-label)",
    lineHeight: "var(--lh-label)",
    fontWeight: "var(--fw-medium)",
    letterSpacing: "var(--tr-label)",
    textTransform: "uppercase",
    color: active ? "var(--text-secondary)" : "var(--text-muted)",
    userSelect: "none",
  };
  if (!sortable) {
    return <th style={base}>{children}</th>;
  }
  return (
    <th
      tabIndex={0}
      aria-sort={active ? "ascending" : "none"}
      className="v2-sort-th v2-focus-inset"
      style={{ ...base, cursor: "pointer" }}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {children}
        {active ? <ArrowUpIcon size={12} /> : <ArrowUpDownIcon size={12} style={{ opacity: 0.5 }} />}
      </span>
    </th>
  );
}

function AtRiskRow({ r }: { r: CommandCenterRow }) {
  const status = formatDueStatus(r.days_to_due_date, r.filing_status, r.blockers_count);
  const returnLabel = r.return_type === "GSTR1" ? "GSTR-1" : r.return_type === "GSTR3B" ? "GSTR-3B" : r.return_type;
  const initials = initialsFrom(r.client_name);
  return (
    <tr className="v2-row" style={{ height: 56, borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "0 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Monogram initials={initials} />
          <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
            <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {r.client_name}
            </span>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
              {r.scheme} · period {formatPeriod(r.period)}
            </span>
          </span>
        </div>
      </td>
      <td className="mono" style={{ padding: "0 12px", color: "var(--text-secondary)" }}>{r.gstin}</td>
      <td style={{ padding: "0 12px", fontSize: 14, color: "var(--text-primary)" }}>{returnLabel}</td>
      <td style={{ padding: "0 12px", fontSize: 14, color: "var(--text-primary)" }} className="tabular">{formatDueDate(r.days_to_due_date)}</td>
      <td style={{ padding: "0 12px", textAlign: "right", fontSize: 14, fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }} className="tabular">
        {r.itc_at_risk_paise > 0 ? formatPaise(r.itc_at_risk_paise) : "—"}
      </td>
      <td style={{ padding: "0 12px" }}>
        <StatusPill tone={status.tone as StatusTone}>{status.label}</StatusPill>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <MiniAvatar initials="—" />
          <span style={{ fontSize: 14, color: "var(--text-muted)" }}>Unassigned</span>
        </span>
      </td>
      <td style={{ padding: "0 24px", textAlign: "right" }}>
        <button
          type="button"
          aria-label="Row actions"
          className="v2-row-actions v2-focus"
          style={{
            width: 28, height: 28, display: "inline-flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-chip)", background: "transparent",
            color: "var(--text-secondary)", cursor: "pointer",
          }}
        >
          <MoreHorizontalIcon size={16} />
        </button>
      </td>
    </tr>
  );
}

function ToolbarButton({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      className="v2-hover-tint v2-focus"
      style={{
        display: "flex", alignItems: "center", gap: 6, height: 32, padding: "0 10px",
        border: 0, borderRadius: "var(--radius-input)",
        background: "transparent", color: "var(--text-secondary)",
        font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
      }}
    >
      {icon}
      {label}
    </button>
  );
}

/* --------------------------------- Helpers --------------------------------- */

function deriveUpcomingCount(cal: ReturnType<typeof useDashboardData>["data"]["calendar"]): number | null {
  if (!cal) return null;
  return cal.rows.filter(
    (r) => r.filing_status !== "filed" && r.days_out >= 0 && r.days_out <= 7,
  ).length;
}

function deriveFiledSub(cc: ReturnType<typeof useDashboardData>["data"]["commandCenter"]): string {
  if (!cc || cc.summary.total_rows === 0) return "—";
  const pct = Math.round((cc.summary.filed_count / cc.summary.total_rows) * 100);
  return `${pct}% of ${cc.summary.total_rows} filings`;
}

function formatPeriod(period: string): string {
  if (!/^[0-9]{6}$/.test(period)) return period;
  const year = period.slice(0, 4);
  const month = parseInt(period.slice(4), 10);
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month - 1] ?? "";
  return `${abbr} ${year}`;
}
