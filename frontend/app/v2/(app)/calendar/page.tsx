import type { CSSProperties } from "react";
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

type EventTone = "success" | "warning" | "danger" | "accent" | "neutral";
type Rail = "solid" | "dashed";

type CalEvent = {
  badge: string;
  label: string;
  tone: EventTone;
  rail?: Rail;
  anchor?: boolean;
};

type Cell = {
  day: number;
  muted?: boolean;
  weekend?: boolean;
  today?: boolean;
  events?: CalEvent[];
  more?: number;
};

// August 2026 — Sat Aug 1 starts the month. Grid begins with Mon Jul 27.
const CAL: Cell[] = [
  { day: 27, muted: true }, { day: 28, muted: true }, { day: 29, muted: true }, { day: 30, muted: true },
  { day: 31, muted: true }, { day: 1, weekend: true }, { day: 2, weekend: true },
  { day: 3 }, { day: 4 },
  { day: 5, events: [{ badge: "GST-1", label: "Q1 · 2 clients — 8d overdue", tone: "danger", rail: "solid" }] },
  { day: 6, events: [{ badge: "AOC", label: "Q4 26 · 1 client — 7d overdue", tone: "danger", rail: "solid" }] },
  { day: 7, events: [{ badge: "TDS", label: "Jul · 24 clients · pay today", tone: "warning", rail: "solid" }] },
  { day: 8, weekend: true }, { day: 9, weekend: true },
  { day: 10, events: [
    { badge: "GST-7", label: "8 clients", tone: "warning", rail: "solid" },
    { badge: "GST-8", label: "3 clients", tone: "warning", rail: "solid" },
  ] },
  { day: 11, events: [
    { badge: "GST-1", label: "Ramesh Textiles", tone: "danger", rail: "solid" },
    { badge: "GST-1", label: "CloudMint Tech", tone: "danger", rail: "solid" },
    { badge: "GST-1", label: "Nova Exports", tone: "danger", rail: "solid" },
  ], more: 44 },
  { day: 12, events: [{ badge: "GST-1", label: "filed · Priya M.", tone: "success", rail: "solid" }] },
  { day: 13, today: true, events: [
    { badge: "GST-3B", label: "draft · Arjun D.", tone: "accent", rail: "solid" },
    { badge: "DIR", label: "3 KYC filing prep", tone: "neutral", rail: "dashed" },
  ] },
  { day: 14, events: [{ badge: "GST-1", label: "late filing · 3 clients", tone: "warning", rail: "solid" }] },
  { day: 15, weekend: true, events: [
    { badge: "PF", label: "& ESI · 62 clients", tone: "warning", rail: "solid" },
    { badge: "TDS", label: "Jul challan late fee", tone: "warning", rail: "solid" },
  ] },
  { day: 16, weekend: true },
  { day: 17, events: [{ badge: "GST-3B", label: "QRMP quarter payment", tone: "warning", rail: "solid" }] },
  { day: 18 }, { day: 19 },
  { day: 20, events: [
    { badge: "GST-3B", label: "Ramesh Textiles", tone: "danger", rail: "solid", anchor: true },
    { badge: "GST-3B", label: "Sundaram Auto", tone: "danger", rail: "solid" },
    { badge: "GST-3B", label: "Meghna Logistics", tone: "danger", rail: "solid" },
  ], more: 81 },
  { day: 21 },
  { day: 22, weekend: true, events: [{ badge: "GST-3B", label: "Cat-X states ≤ 5 Cr", tone: "warning", rail: "solid" }] },
  { day: 23, weekend: true },
  { day: 24, events: [{ badge: "GST-3B", label: "Cat-Y states", tone: "warning", rail: "solid" }] },
  { day: 25, events: [{ badge: "PT", label: "MH monthly return", tone: "warning", rail: "solid" }] },
  { day: 26 }, { day: 27 },
  { day: 28, events: [{ badge: "GST-11", label: "UIN holders", tone: "warning", rail: "solid" }] },
  { day: 29, weekend: true },
  { day: 30, weekend: true, events: [{ badge: "TCS", label: "Q1 return · 27EQ", tone: "warning", rail: "solid" }] },
  { day: 31, events: [
    { badge: "TDS", label: "Q1 · 24Q · 26Q", tone: "danger", rail: "solid" },
    { badge: "TAR", label: "Sec 44AB audit start", tone: "warning", rail: "solid" },
  ] },
  { day: 1, muted: true }, { day: 2, muted: true }, { day: 3, muted: true }, { day: 4, muted: true },
  { day: 5, weekend: true, muted: true }, { day: 6, weekend: true, muted: true },
];

type RailCard = {
  badge: string;
  title: string;
  amount?: string;
  status: { label: string; tone: StatusTone };
  ownerInitials: string;
  danger?: boolean;
};

type RailGroup = {
  label: string;
  active?: boolean;
  cards: RailCard[];
};

const RAIL_GROUPS: RailGroup[] = [
  { label: "Today · Thu 13 Aug", active: true, cards: [
    { badge: "GST-3B", title: "Ramesh Textiles", amount: "₹4.2L", status: { label: "In progress", tone: "accent" }, ownerInitials: "AD" },
    { badge: "DIR", title: "3 KYC prep · CloudMint", status: { label: "Scheduled", tone: "neutral" }, ownerInitials: "PM" },
  ] },
  { label: "Tomorrow · Fri 14 Aug", cards: [
    { badge: "GST-1", title: "late · Nova Exports", status: { label: "Due today", tone: "warning" }, ownerInitials: "AD" },
  ] },
  { label: "Sat 15 Aug", cards: [
    { badge: "PF", title: "& ESI · 62 clients", amount: "₹18.6L", status: { label: "Batch task", tone: "accent" }, ownerInitials: "TM" },
    { badge: "TDS", title: "Jul late fee · 12 clients", status: { label: "Escalated", tone: "danger" }, ownerInitials: "PM" },
  ] },
  { label: "Mon 17 Aug", cards: [
    { badge: "GST-3B", title: "QRMP · 8 clients", amount: "₹6.4L", status: { label: "Due in 4 days", tone: "warning" }, ownerInitials: "PM" },
  ] },
  { label: "Thu 20 Aug", cards: [
    { badge: "GST-3B", title: "monthly · 84 clients", amount: "₹2.14 Cr", status: { label: "Blocker · high volume", tone: "danger" }, ownerInitials: "TM", danger: true },
  ] },
];

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

export default function CalendarPage() {
  return (
    <div style={{ display: "flex", alignItems: "stretch", flex: 1, minWidth: 0 }}>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
        <PageHeader />
        <ControlsRow />
        <CalendarGrid />
      </div>
      <NextSevenDaysRail />
    </div>
  );
}

/* --------------------------------- Header --------------------------------- */

function PageHeader() {
  return (
    <div style={{ flex: "none", padding: "24px 32px 0", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24 }}>
      <h1
        style={{
          margin: 0,
          fontSize: "var(--fs-h1)",
          lineHeight: "var(--lh-h1)",
          fontWeight: "var(--fw-semi)",
          letterSpacing: "var(--tr-h1)",
          color: "var(--text-primary)",
        }}
      >
        Compliance Calendar
      </h1>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <SecondaryButton>Sync to Google Calendar</SecondaryButton>
        <button
          type="button"
          className="v2-btn-primary v2-focus"
          style={{
            height: 32,
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "0 14px",
            border: 0,
            borderRadius: "var(--radius-input)",
            background: "var(--accent)",
            color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`,
            cursor: "pointer",
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
        height: 32,
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "0 12px",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-input)",
        background: "var(--surface)",
        color: "var(--text-primary)",
        font: `500 13px/20px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

/* --------------------------------- Controls --------------------------------- */

function ControlsRow() {
  return (
    <div style={{ flex: "none", padding: "12px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <NavArrow aria-label="Previous month"><ChevronLeftIcon size={14} /></NavArrow>
        <span style={{ minWidth: 120, textAlign: "center", fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          August 2026
        </span>
        <NavArrow aria-label="Next month"><ChevronRightIcon size={14} /></NavArrow>
        <button
          type="button"
          className="v2-btn-secondary v2-focus"
          style={{
            height: 32,
            padding: "0 12px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`,
            cursor: "pointer",
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
        <FilterChip>Return type: All 15</FilterChip>
        <FilterChip>Client: All 142</FilterChip>
        <FilterChip>Owner: All 8</FilterChip>
        <FilterChip>Status: All</FilterChip>
        <div style={{ width: 1, height: 20, background: "var(--border)" }} />
        <div
          className="v2-search-wrap"
          style={{
            width: 240,
            boxSizing: "border-box",
            height: 32,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 10px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
          }}
        >
          <SearchIcon size={16} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search calendar"
            style={{
              flex: 1,
              minWidth: 0,
              border: 0,
              outline: 0,
              background: "transparent",
              font: `400 13px/20px var(--font-sans-v2)`,
              color: "var(--text-primary)",
            }}
          />
        </div>
        <button
          type="button"
          aria-label="All filters"
          className="v2-btn-secondary v2-focus"
          style={{
            width: 32,
            height: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            color: "var(--text-secondary)",
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
        width: 32,
        height: 32,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-input)",
        background: "var(--surface)",
        color: "var(--text-secondary)",
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
        padding: "0 14px",
        border: 0,
        borderLeft: undefined,
        background: active ? "var(--accent-soft)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        font: `500 13px/20px var(--font-sans-v2)`,
        cursor: "pointer",
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
        height: 32,
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "0 10px",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-input)",
        background: "var(--surface)",
        color: "var(--text-secondary)",
        font: `500 12px/16px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
      <ChevronDownIcon size={12} />
    </button>
  );
}

/* --------------------------------- Calendar grid --------------------------------- */

function CalendarGrid() {
  return (
    <div style={{ flex: 1, padding: "16px 32px 32px", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div
        style={{
          flex: 1,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-app-card)",
          boxShadow: "var(--shadow-card)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", borderBottom: "1px solid var(--border)" }}>
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
            <span key={d} style={{ padding: "12px 16px", ...LABEL, textAlign: "center" }}>{d}</span>
          ))}
        </div>
        <div
          style={{
            flex: 1,
            display: "grid",
            gridTemplateColumns: "repeat(7, 1fr)",
            gap: 1,
            background: "var(--border)",
          }}
        >
          {CAL.map((cell, i) => <CellView key={i} cell={cell} idx={i} />)}
        </div>
      </div>
    </div>
  );
}

function CellView({ cell, idx }: { cell: Cell; idx: number }) {
  const bg = cell.weekend ? "var(--bg)" : "var(--surface)";
  const dayColor = cell.today
    ? "#fff"
    : cell.muted
    ? "var(--text-muted)"
    : cell.weekend
    ? "var(--text-muted)"
    : "var(--text-secondary)";

  return (
    <div
      style={{
        minHeight: 132,
        padding: 8,
        background: bg,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        opacity: cell.muted ? 0.65 : 1,
        position: "relative",
      }}
    >
      {cell.today ? (
        <span
          style={{
            width: 28,
            height: 28,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 6,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            fontSize: 13,
            fontWeight: "var(--fw-semi)",
            marginBottom: 2,
          }}
        >
          {cell.day}
        </span>
      ) : (
        <span style={{ fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: dayColor, padding: "2px 4px" }}>
          {cell.day}
        </span>
      )}
      {cell.events?.map((e, i) => (
        <div key={i} style={{ position: "relative" }}>
          <EventPill event={e} />
          {e.anchor && <PopoverAnchor />}
        </div>
      ))}
      {cell.more != null && (
        <a href="#" className="v2-focus" style={{ fontSize: 11, lineHeight: "16px", color: "var(--text-secondary)", padding: "0 6px", textDecoration: "none" }}>
          +{cell.more} more
        </a>
      )}
    </div>
  );
}

function EventPill({ event }: { event: CalEvent }) {
  const dashed = event.rail === "dashed";
  const railColor = toneFg[event.tone];
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        width: "100%",
        minHeight: 22,
        padding: "2px 6px",
        borderLeft: `3px ${dashed ? "dashed" : "solid"} ${railColor}`,
        borderTop: 0, borderRight: 0, borderBottom: 0,
        borderRadius: 6,
        background: toneSoft[event.tone],
        color: toneFg[event.tone],
        font: `500 12px/16px var(--font-sans-v2)`,
        cursor: "pointer",
        textAlign: "left",
        boxShadow: event.anchor ? "0 0 0 1.5px var(--accent)" : undefined,
      }}
    >
      <span
        style={{
          flex: "none",
          height: 16,
          padding: "0 4px",
          display: "flex",
          alignItems: "center",
          border: "1px solid var(--border)",
          borderRadius: 4,
          background: "var(--surface)",
          color: "var(--text-secondary)",
          fontSize: 10,
          fontWeight: "var(--fw-semi)",
          letterSpacing: "var(--tr-label)",
        }}
      >
        {event.badge}
      </span>
      <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {event.label}
      </span>
    </button>
  );
}

/* --------------------------------- Popover --------------------------------- */

function PopoverAnchor() {
  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 8px)",
        left: 0,
        width: 360,
        zIndex: 10,
        background: "var(--surface)",
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--radius-app-card)",
        boxShadow: "var(--shadow-event-popover)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              height: 20,
              padding: "0 6px",
              display: "flex",
              alignItems: "center",
              border: "1px solid var(--border)",
              borderRadius: 4,
              background: "var(--surface)",
              color: "var(--text-secondary)",
              fontSize: 10,
              fontWeight: "var(--fw-semi)",
              letterSpacing: "var(--tr-label)",
            }}
          >
            GST-3B
          </span>
          <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            GSTR-3B
          </span>
        </div>
        <button
          type="button"
          aria-label="Close"
          className="v2-hover-tint v2-focus"
          style={{ width: 24, height: 24, display: "flex", alignItems: "center", justifyContent: "center", border: 0, borderRadius: "var(--radius-chip)", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}
        >
          <XIcon size={14} />
        </button>
      </div>
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
        GSTR-3B · July 2026 · Due 20 Aug 2026 (7d)
      </span>
      <div style={{ height: 1, background: "var(--border)" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          style={{
            width: 32, height: 32, flex: "none",
            borderRadius: 8,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 12, fontWeight: "var(--fw-semi)",
          }}
        >
          RT
        </span>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            Ramesh Textiles Pvt Ltd
          </span>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
            Cotton yarn &amp; grey fabric
          </span>
        </div>
        <ChevronRightIcon size={16} style={{ color: "var(--text-muted)" }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
        <PopVal label="Turnover" value="₹1.42 Cr" />
        <PopVal label="Tax payable" value="₹4,26,780" />
        <PopVal label="ITC available" value="₹1,18,450" />
        <PopVal label="Days to due" value="7 days" />
      </div>
      <div style={{ height: 1, background: "var(--border)" }} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <StatusPill tone="danger">Blocker · high volume</StatusPill>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Change status</a>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <MiniAvatar initials="AD" />
        <span style={{ flex: 1, fontSize: 13, color: "var(--text-secondary)" }}>Arjun Devarajan</span>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Reassign</a>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <button
          type="button"
          className="v2-btn-primary v2-focus"
          style={{
            height: 32,
            border: 0,
            borderRadius: "var(--radius-input)",
            background: "var(--accent)",
            color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`,
            cursor: "pointer",
          }}
        >
          Start filing
        </button>
        <button
          type="button"
          className="v2-btn-secondary v2-focus"
          style={{
            height: 32,
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "transparent",
            color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`,
            cursor: "pointer",
          }}
        >
          Open in workspace
        </button>
      </div>
    </div>
  );
}

function PopVal({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</span>
      <span className="tabular" style={{ fontSize: 13, fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}

/* --------------------------------- Rail --------------------------------- */

function NextSevenDaysRail() {
  return (
    <aside
      style={{
        width: 320,
        flex: "none",
        boxSizing: "border-box",
        background: "var(--surface)",
        borderLeft: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div style={{ height: 72, flex: "none", padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Next 7 days</span>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>Sorted by due date</span>
        </div>
        <button
          type="button"
          aria-label="Group by client"
          title="Group by client"
          className="v2-hover-tint v2-focus"
          style={{
            width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-chip)",
            background: "transparent",
            color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          <FilterIcon size={16} />
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", display: "flex", flexDirection: "column" }}>
        {RAIL_GROUPS.map((g) => (
          <div key={g.label}>
            <div
              style={{
                height: 32,
                padding: "0 16px",
                background: "var(--bg)",
                display: "flex",
                alignItems: "center",
                fontSize: 11,
                fontWeight: "var(--fw-medium)",
                letterSpacing: "var(--tr-label)",
                textTransform: "uppercase",
                color: g.active ? "var(--accent)" : "var(--text-muted)",
              }}
            >
              {g.label}
            </div>
            <div style={{ padding: "8px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {g.cards.map((c, i) => <RailCardView key={i} c={c} />)}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          height: 72,
          flex: "none",
          borderTop: "1px solid var(--border)",
          padding: "12px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }}>Week load: 87% capacity</span>
          <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Rebalance workload →</a>
        </div>
        <div style={{ height: 2, borderRadius: "var(--radius-pill)", background: "var(--border)", overflow: "hidden" }}>
          <div style={{ width: "87%", height: 2, background: "var(--warning)" }} />
        </div>
      </div>
    </aside>
  );
}

function RailCardView({ c }: { c: RailCard }) {
  const tone = c.status.tone as EventTone;
  const railColor = tone === "neutral" ? "var(--border-strong)" : toneFg[tone];
  const cardBg = c.danger ? "var(--danger-soft)" : "var(--surface)";
  const badgeBg = c.danger ? "var(--surface)" : "var(--surface)";
  return (
    <div
      style={{
        minHeight: 68,
        padding: 12,
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${railColor}`,
        borderRadius: "var(--radius-app-card)",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        background: cardBg,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            flex: "none",
            height: 20,
            padding: "0 6px",
            display: "flex",
            alignItems: "center",
            border: "1px solid var(--border)",
            borderRadius: 4,
            background: badgeBg,
            color: "var(--text-secondary)",
            fontSize: 10,
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-label)",
          }}
        >
          {c.badge}
        </span>
        <span style={{ flex: 1, minWidth: 0, fontSize: 14, fontWeight: "var(--fw-medium)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {c.title}
        </span>
        {c.amount && (
          <span className="tabular" style={{ flex: "none", fontSize: 12, color: c.danger ? "var(--text-primary)" : "var(--text-muted)", fontWeight: c.danger ? 500 : 400 }}>
            {c.amount}
          </span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <StatusPill tone={c.status.tone}>{c.status.label}</StatusPill>
        <span style={{ flex: 1 }} />
        <MiniAvatar initials={c.ownerInitials} />
        <button
          type="button"
          aria-label="More actions"
          className="v2-hover-tint v2-focus"
          style={{
            width: 20, height: 20,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: 4,
            background: "transparent",
            color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          <MoreHorizontalIcon size={14} />
        </button>
      </div>
    </div>
  );
}
