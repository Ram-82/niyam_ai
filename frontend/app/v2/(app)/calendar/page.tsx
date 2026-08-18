"use client";

import Link from "next/link";
import { useState, type CSSProperties } from "react";
import {
  BellIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FilterIcon,
  MoreHorizontalIcon,
  SearchIcon,
  XIcon,
} from "@/components/v2/icons";
import { MiniAvatar } from "@/components/v2/ui/Monogram";
import { StatusPill, type StatusTone } from "@/components/v2/ui/StatusPill";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { LoadingState } from "@/components/v2/ui/LoadingState";
import {
  buildMonthGrid,
  buildRailGroups,
  formatDueDate,
  formatPeriod,
  initialsFrom,
  prettyReturnBadge,
  prettyReturnType,
  statusForRow,
  useCalendarData,
  type CalendarCell,
  type CalendarRow,
  type EventTone,
  type RailGroup,
} from "./useCalendarData";

/* --------------------------------- Styles --------------------------------- */

const LABEL: CSSProperties = {
  fontSize: "var(--fs-label)",
  lineHeight: "var(--lh-label)",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

const toneSoft: Record<EventTone, string> = {
  success: "var(--success-soft)",
  warning: "var(--warning-soft)",
  danger: "var(--danger-soft)",
  accent: "var(--accent-soft)",
  neutral: "var(--row-hover)",
};
const toneFg: Record<EventTone, string> = {
  success: "var(--success)",
  warning: "var(--warning)",
  danger: "var(--danger)",
  accent: "var(--accent)",
  neutral: "var(--text-secondary)",
};

/* --------------------------------- Page --------------------------------- */

export default function CalendarPage() {
  const { data, loading, error, reload } = useCalendarData({ horizonDays: 90, lookbackDays: 30 });
  const [viewDate, setViewDate] = useState<Date>(() => new Date());
  const [selected, setSelected] = useState<{ iso: string; key: string } | null>(null);

  const rows = data?.rows ?? [];
  const todayIso = data?.today ?? new Date().toISOString().slice(0, 10);
  const cells = buildMonthGrid(rows, todayIso, viewDate);
  const railGroups = buildRailGroups(rows, todayIso);

  const monthLabel = viewDate.toLocaleDateString("en-IN", { month: "long", year: "numeric" });

  const goPrev = () => setViewDate((d) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 1, 1)));
  const goNext = () => setViewDate((d) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)));
  const goToday = () => setViewDate(data ? new Date(data.today) : new Date());

  return (
    <div style={{ display: "flex", alignItems: "stretch", flex: 1, minWidth: 0 }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
        <PageHeader />
        {error && (
          <div style={{ padding: "12px 32px 0" }}>
            <ErrorBanner message={`Could not load calendar: ${error}`} onRetry={reload} />
          </div>
        )}
        <ControlsRow
          monthLabel={monthLabel}
          onPrev={goPrev}
          onNext={goNext}
          onToday={goToday}
        />
        <CalendarGrid
          cells={cells}
          loading={loading && !data}
          selected={selected}
          onSelect={setSelected}
          onClose={() => setSelected(null)}
        />
      </div>
      <NextSevenDaysRail groups={railGroups} loading={loading && !data} />
    </div>
  );
}

/* --------------------------------- Header --------------------------------- */

function PageHeader() {
  return (
    <div style={{ flex: "none", padding: "24px 32px 0", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24 }}>
      <h1 style={{
        margin: 0,
        fontSize: "var(--fs-h1)",
        lineHeight: "var(--lh-h1)",
        fontWeight: "var(--fw-semi)",
        letterSpacing: "var(--tr-h1)",
        color: "var(--text-primary)",
      }}>
        Compliance Calendar
      </h1>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <SecondaryButton>Sync to Google Calendar</SecondaryButton>
        <button
          type="button"
          className="v2-btn-primary v2-focus"
          style={{
            height: 32, display: "flex", alignItems: "center", gap: 6,
            padding: "0 14px", border: 0, borderRadius: "var(--radius-input)",
            background: "var(--accent)", color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          <BellIcon size={14} />
          Add reminder
        </button>
      </div>
    </div>
  );
}

function SecondaryButton({ children }: { children: React.ReactNode }) {
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
      {children}
    </button>
  );
}

/* --------------------------------- Controls --------------------------------- */

function ControlsRow({
  monthLabel, onPrev, onNext, onToday,
}: {
  monthLabel: string;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}) {
  return (
    <div style={{ flex: "none", padding: "12px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <NavArrow aria-label="Previous month" onClick={onPrev}><ChevronLeftIcon size={14} /></NavArrow>
        <span style={{ minWidth: 140, textAlign: "center", fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          {monthLabel}
        </span>
        <NavArrow aria-label="Next month" onClick={onNext}><ChevronRightIcon size={14} /></NavArrow>
        <button
          type="button"
          onClick={onToday}
          className="v2-btn-secondary v2-focus"
          style={{
            height: 32, padding: "0 12px",
            border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
            background: "var(--surface)", color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          Today
        </button>
        <div style={{ width: 1, height: 20, background: "var(--border)" }} />
        <div style={{ height: 32, display: "flex", alignItems: "stretch", border: "1px solid var(--border)", borderRadius: "var(--radius-input)", overflow: "hidden" }}>
          <SegBtn active>Month</SegBtn>
          <SegBtn>Week</SegBtn>
          <SegBtn>Agenda</SegBtn>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <FilterChip>Return type: All</FilterChip>
        <FilterChip>Client: All</FilterChip>
        <FilterChip>Owner: All</FilterChip>
        <FilterChip>Status: All</FilterChip>
        <div style={{ width: 1, height: 20, background: "var(--border)" }} />
        <div className="v2-search-wrap" style={{
          width: 240, boxSizing: "border-box", height: 32,
          display: "flex", alignItems: "center", gap: 8, padding: "0 10px",
          border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
          background: "var(--surface)",
        }}>
          <SearchIcon size={16} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search calendar"
            style={{
              flex: 1, minWidth: 0, border: 0, outline: 0,
              background: "transparent",
              font: `400 13px/20px var(--font-sans-v2)`,
              color: "var(--text-primary)",
            }}
          />
        </div>
        <button
          type="button" aria-label="All filters"
          className="v2-btn-secondary v2-focus"
          style={{
            width: 32, height: 32,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
            background: "var(--surface)", color: "var(--text-secondary)",
            cursor: "pointer",
          }}
        >
          <FilterIcon size={16} />
        </button>
      </div>
    </div>
  );
}

function NavArrow({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className="v2-hover-tint v2-focus"
      style={{
        width: 32, height: 32,
        display: "flex", alignItems: "center", justifyContent: "center",
        border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
        background: "var(--surface)", color: "var(--text-secondary)",
        cursor: "pointer",
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

function SegBtn({ children, active }: { children: React.ReactNode; active?: boolean }) {
  return (
    <button
      type="button"
      className="v2-focus-inset"
      style={{
        padding: "0 14px", border: 0,
        background: active ? "var(--accent-soft)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function FilterChip({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      style={{
        height: 32, display: "flex", alignItems: "center", gap: 6,
        padding: "0 10px", border: "1px solid var(--border)",
        borderRadius: "var(--radius-input)", background: "var(--surface)",
        color: "var(--text-secondary)", font: `500 12px/16px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
      <ChevronDownIcon size={12} />
    </button>
  );
}

/* --------------------------------- Calendar grid --------------------------------- */

function CalendarGrid({
  cells, loading, selected, onSelect, onClose,
}: {
  cells: CalendarCell[];
  loading: boolean;
  selected: { iso: string; key: string } | null;
  onSelect: (sel: { iso: string; key: string }) => void;
  onClose: () => void;
}) {
  return (
    <div style={{ flex: 1, padding: "16px 32px 32px", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div style={{
        flex: 1, background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)",
        boxShadow: "var(--shadow-card)", overflow: "hidden",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", borderBottom: "1px solid var(--border)" }}>
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
            <span key={d} style={{ padding: "12px 16px", ...LABEL, textAlign: "center" }}>{d}</span>
          ))}
        </div>
        {loading ? (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 13 }}>
            Loading calendar…
          </div>
        ) : (
          <div style={{
            flex: 1, display: "grid", gridTemplateColumns: "repeat(7, 1fr)",
            gap: 1, background: "var(--border)",
          }}>
            {cells.map((cell, i) => (
              <CellView
                key={i}
                cell={cell}
                selected={selected}
                onSelect={onSelect}
                onClose={onClose}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CellView({
  cell, selected, onSelect, onClose,
}: {
  cell: CalendarCell;
  selected: { iso: string; key: string } | null;
  onSelect: (sel: { iso: string; key: string }) => void;
  onClose: () => void;
}) {
  const bg = cell.weekend ? "var(--bg)" : "var(--surface)";
  const dayColor = cell.today
    ? "#fff"
    : cell.muted ? "var(--text-muted)"
    : cell.weekend ? "var(--text-muted)"
    : "var(--text-secondary)";
  const activePill = selected?.iso === cell.isoDate ? selected.key : null;

  return (
    <div style={{
      minHeight: 132, padding: 8, background: bg,
      display: "flex", flexDirection: "column", gap: 4,
      opacity: cell.muted ? 0.65 : 1, position: "relative",
    }}>
      {cell.today ? (
        <span style={{
          width: 28, height: 28,
          display: "flex", alignItems: "center", justifyContent: "center",
          borderRadius: 6, background: "var(--accent)", color: "#fff",
          fontSize: 13, fontWeight: "var(--fw-semi)", marginBottom: 2,
        }}>
          {cell.day}
        </span>
      ) : (
        <span style={{
          fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-medium)",
          color: dayColor, padding: "2px 4px",
        }}>
          {cell.day}
        </span>
      )}
      {cell.events.map((e) => (
        <div key={e.key} style={{ position: "relative" }}>
          <EventPill
            event={e}
            anchor={activePill === e.key}
            onClick={() => onSelect({ iso: cell.isoDate, key: e.key })}
          />
          {activePill === e.key && (
            <PopoverAnchor event={e} isoDate={cell.isoDate} onClose={onClose} />
          )}
        </div>
      ))}
      {cell.more != null && (
        <span style={{ fontSize: 11, lineHeight: "16px", color: "var(--text-secondary)", padding: "0 6px" }}>
          +{cell.more} more
        </span>
      )}
    </div>
  );
}

function EventPill({
  event, anchor, onClick,
}: {
  event: CalendarCell["events"][number];
  anchor: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="v2-focus"
      style={{
        display: "flex", alignItems: "center", gap: 6,
        width: "100%", minHeight: 22, padding: "2px 6px",
        borderLeft: `3px solid ${toneFg[event.tone]}`,
        borderTop: 0, borderRight: 0, borderBottom: 0,
        borderRadius: 6, background: toneSoft[event.tone],
        color: toneFg[event.tone],
        font: `500 12px/16px var(--font-sans-v2)`,
        cursor: "pointer", textAlign: "left",
        boxShadow: anchor ? "0 0 0 1.5px var(--accent)" : undefined,
      }}
    >
      <span style={{
        flex: "none", height: 16, padding: "0 4px",
        display: "flex", alignItems: "center",
        border: "1px solid var(--border)", borderRadius: 4,
        background: "var(--surface)", color: "var(--text-secondary)",
        fontSize: 10, fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-label)",
      }}>
        {event.badge}
      </span>
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {event.label}
      </span>
    </button>
  );
}

/* --------------------------------- Popover --------------------------------- */

function PopoverAnchor({
  event, isoDate, onClose,
}: {
  event: CalendarCell["events"][number];
  isoDate: string;
  onClose: () => void;
}) {
  const first = event.rows[0];
  return (
    <div style={{
      position: "absolute", top: "calc(100% + 8px)", left: 0,
      width: 360, zIndex: 10,
      background: "var(--surface)",
      border: "1px solid var(--border-strong)",
      borderRadius: "var(--radius-app-card)",
      boxShadow: "var(--shadow-event-popover)",
      padding: 16, display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            height: 20, padding: "0 6px",
            display: "flex", alignItems: "center",
            border: "1px solid var(--border)", borderRadius: 4,
            background: "var(--surface)", color: "var(--text-secondary)",
            fontSize: 10, fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-label)",
          }}>
            {event.badge}
          </span>
          <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            {prettyReturnType(first.return_type)}
          </span>
        </div>
        <button
          type="button" aria-label="Close" onClick={onClose}
          className="v2-hover-tint v2-focus"
          style={{
            width: 24, height: 24,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-chip)",
            background: "transparent", color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          <XIcon size={14} />
        </button>
      </div>
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
        {prettyReturnType(first.return_type)} · {formatPeriod(first.period)} · Due {formatDueDate(isoDate)} ({first.days_out >= 0 ? `${first.days_out}d` : `${Math.abs(first.days_out)}d ago`})
      </span>
      <div style={{ height: 1, background: "var(--border)" }} />

      {event.rows.length === 1 ? (
        <SinglePopBody row={first} />
      ) : (
        <MultiPopBody rows={event.rows} />
      )}
    </div>
  );
}

function SinglePopBody({ row }: { row: CalendarRow }) {
  const status = statusForRow(row);
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{
          width: 32, height: 32, flex: "none",
          borderRadius: 8, background: "var(--accent-soft)", color: "var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: "var(--fw-semi)",
        }}>
          {initialsFrom(row.client_trade_name)}
        </span>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <span style={{
            fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)",
            color: "var(--text-primary)",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {row.client_trade_name}
          </span>
          <span className="mono" style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
            {row.gstin}
          </span>
        </div>
        <ChevronRightIcon size={16} style={{ color: "var(--text-muted)" }} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
        <PopVal label="Scheme" value={row.scheme.toUpperCase()} />
        <PopVal label="Days to due" value={row.days_out >= 0 ? `${row.days_out} days` : `${Math.abs(row.days_out)} days ago`} />
        <PopVal label="Filing status" value={row.filing_status ?? "Not started"} />
        <PopVal label="Reminders sent" value={String(row.reminders_sent)} />
      </div>
      <div style={{ height: 1, background: "var(--border)" }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <StatusPill tone={statusToneToStatusTone(status.tone)}>{status.label}</StatusPill>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <MiniAvatar initials="—" />
        <span style={{ flex: 1, fontSize: 13, color: "var(--text-muted)" }}>Unassigned</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <Link
          href={`/v2/filings?status=draft`}
          className="v2-btn-primary v2-focus"
          style={{
            height: 32, display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-input)",
            background: "var(--accent)", color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
            textDecoration: "none",
          }}
        >
          Open in filings
        </Link>
        <Link
          href={`/v2/clients`}
          className="v2-btn-secondary v2-focus"
          style={{
            height: 32, display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
            background: "transparent", color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
            textDecoration: "none",
          }}
        >
          Open client
        </Link>
      </div>
    </>
  );
}

function MultiPopBody({ rows }: { rows: CalendarRow[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 260, overflow: "auto" }}>
      {rows.map((r) => (
        <div key={`${r.gstin_profile_id}-${r.period}`} style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "6px 8px", borderRadius: "var(--radius-chip)",
        }}>
          <span style={{
            width: 24, height: 24, flex: "none",
            borderRadius: 6, background: "var(--accent-soft)", color: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, fontWeight: "var(--fw-semi)",
          }}>
            {initialsFrom(r.client_trade_name)}
          </span>
          <span style={{
            flex: 1, minWidth: 0, fontSize: 13, color: "var(--text-primary)",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {r.client_trade_name}
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {r.gstin}
          </span>
        </div>
      ))}
    </div>
  );
}

function PopVal({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</span>
      <span className="tabular" style={{ fontSize: 13, fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

function statusToneToStatusTone(t: EventTone): StatusTone {
  if (t === "accent") return "accent";
  if (t === "neutral") return "neutral";
  return t;
}

/* --------------------------------- Rail --------------------------------- */

function NextSevenDaysRail({ groups, loading }: { groups: RailGroup[]; loading: boolean }) {
  const total = groups.reduce((s, g) => s + g.rows.length, 0);
  return (
    <aside style={{
      width: 320, flex: "none", boxSizing: "border-box",
      background: "var(--surface)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column", minHeight: 0,
    }}>
      <div style={{
        height: 72, flex: "none", padding: "16px 20px",
        borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            Next 7 days
          </span>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
            {loading ? "Loading…" : `${total} filing${total === 1 ? "" : "s"} · sorted by due date`}
          </span>
        </div>
        <button
          type="button" aria-label="Group by client" title="Group by client"
          className="v2-hover-tint v2-focus"
          style={{
            width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-chip)",
            background: "transparent", color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          <FilterIcon size={16} />
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
        {loading ? (
          <LoadingState variant="inline" />
        ) : groups.length === 0 ? (
          <EmptyState variant="inline" message="No unfiled returns due in the next 7 days." />
        ) : (
          groups.map((g) => (
            <div key={g.isoDate}>
              <div style={{
                height: 32, padding: "0 16px",
                background: "var(--bg)",
                display: "flex", alignItems: "center",
                fontSize: 11, fontWeight: "var(--fw-medium)",
                letterSpacing: "var(--tr-label)", textTransform: "uppercase",
                color: g.active ? "var(--accent)" : "var(--text-muted)",
              }}>
                {g.label}
              </div>
              <div style={{ padding: "8px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                {g.rows.map((r) => (
                  <RailCardView key={`${r.gstin_profile_id}-${r.period}-${r.return_type}`} row={r} />
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      <div style={{
        height: 72, flex: "none",
        borderTop: "1px solid var(--border)", padding: "12px 16px",
        display: "flex", flexDirection: "column", gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }}>
            {loading ? "Loading…" : `${total} filing${total === 1 ? "" : "s"} on the horizon`}
          </span>
          <Link
            href="/v2/filings?status=draft"
            className="v2-focus"
            style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}
          >
            Open all →
          </Link>
        </div>
      </div>
    </aside>
  );
}

function RailCardView({ row }: { row: CalendarRow }) {
  const status = statusForRow(row);
  const railColor = status.tone === "neutral" ? "var(--border-strong)" : toneFg[status.tone];
  return (
    <div style={{
      minHeight: 68, padding: 12,
      border: "1px solid var(--border)",
      borderLeft: `3px solid ${railColor}`,
      borderRadius: "var(--radius-app-card)",
      display: "flex", flexDirection: "column", gap: 6,
      background: "var(--surface)", cursor: "pointer",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          flex: "none", height: 20, padding: "0 6px",
          display: "flex", alignItems: "center",
          border: "1px solid var(--border)", borderRadius: 4,
          background: "var(--surface)", color: "var(--text-secondary)",
          fontSize: 10, fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-label)",
        }}>
          {prettyReturnBadge(row.return_type)}
        </span>
        <span style={{
          flex: 1, minWidth: 0, fontSize: 14, fontWeight: "var(--fw-medium)",
          color: "var(--text-primary)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {row.client_trade_name}
        </span>
        <span className="tabular" style={{ flex: "none", fontSize: 11, color: "var(--text-muted)" }}>
          {formatPeriod(row.period)}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <StatusPill tone={statusToneToStatusTone(status.tone)}>{status.label}</StatusPill>
        <span style={{ flex: 1 }} />
        <MiniAvatar initials="—" />
        <button
          type="button" aria-label="More actions"
          className="v2-hover-tint v2-focus"
          style={{
            width: 20, height: 20,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: 4,
            background: "transparent", color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          <MoreHorizontalIcon size={14} />
        </button>
      </div>
    </div>
  );
}
