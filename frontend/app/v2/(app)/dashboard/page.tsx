import type { CSSProperties } from "react";
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
import { MiniAvatar, Monogram } from "@/components/v2/ui/Monogram";
import { StatusPill, type StatusTone } from "@/components/v2/ui/StatusPill";

type EventTone = "success" | "warning" | "danger" | "neutral";
type CalCell = {
  day: number;
  muted?: boolean;
  weekend?: boolean;
  today?: boolean;
  events?: { label: string; tone: EventTone; tip: string }[];
  more?: number;
};

const CAL: CalCell[] = [
  { day: 27, muted: true }, { day: 28, muted: true }, { day: 29, muted: true }, { day: 30, muted: true },
  { day: 31, muted: true, events: [{ label: "TDS 24Q overdue · 2", tone: "danger", tip: "TDS 24Q · Q1 FY26-27 · 46 clients · ₹1.82 Cr" }] },
  { day: 1, weekend: true }, { day: 2, weekend: true },
  { day: 3, events: [{ label: "GSTR-7 filed · 9", tone: "success", tip: "GSTR-7 (TDS) · 9 clients filed" }] },
  { day: 4 },
  { day: 5, events: [{ label: "GSTR-3B filed · 12", tone: "success", tip: "GSTR-3B · Jul 2026 · 12 clients · ₹4.06 Cr tax paid" }] },
  { day: 6 },
  { day: 7, events: [
    { label: "GSTR-1 filed · 22", tone: "success", tip: "GSTR-1 · Jul 2026 · 22 clients filed" },
    { label: "IFF filed · 6", tone: "success", tip: "Invoice Furnishing Facility · 6 clients filed" },
  ] },
  { day: 8, weekend: true }, { day: 9, weekend: true },
  { day: 10, events: [{ label: "GSTR-7/8 due · 11", tone: "warning", tip: "GSTR-7 & GSTR-8 · TDS/TCS returns · 11 clients" }] },
  { day: 11, events: [
    { label: "GSTR-1 due · 34", tone: "warning", tip: "GSTR-1 · Jul 2026 · 34 clients · ₹12.4 Cr turnover" },
    { label: "2 at risk", tone: "danger", tip: "Sundaram Auto Components Ltd · ₹42,17,850 at risk" },
  ], more: 3 },
  { day: 12 },
  { day: 13, today: true, events: [
    { label: "GSTR-6 due · 4", tone: "warning", tip: "GSTR-6 · ISD credit distribution · 4 clients" },
    { label: "1 overdue", tone: "danger", tip: "Ramesh Textiles Pvt Ltd · GSTR-3B Jul 2026 · ₹18,42,600" },
  ] },
  { day: 14, events: [{ label: "ROC AOC-4 · 1", tone: "warning", tip: "ROC AOC-4 XBRL · Kalyan Steel Traders · ₹3,26,750" }] },
  { day: 15, weekend: true }, { day: 16, weekend: true },
  { day: 17 },
  { day: 18, events: [{ label: "CMP-08 due · 7", tone: "warning", tip: "CMP-08 · Composition dealers · 7 clients" }] },
  { day: 19 },
  { day: 20, events: [
    { label: "GSTR-3B due · 128", tone: "warning", tip: "GSTR-3B · Jul 2026 · 128 clients · ₹38.6 Cr liability" },
    { label: "PMT-06 due · 19", tone: "warning", tip: "PMT-06 · QRMP monthly payment · 19 clients" },
  ], more: 2 },
  { day: 21 },
  { day: 22, weekend: true }, { day: 23, weekend: true },
  { day: 24 },
  { day: 25, events: [{ label: "PF & ESI due · 63", tone: "warning", tip: "PF & ESI challans · 63 clients · payroll month Jul" }] },
  { day: 26 },
  { day: 27, events: [{ label: "GSTR-9 draft review", tone: "neutral", tip: "GSTR-9 / 9C · FY 2025-26 · internal review milestone" }] },
  { day: 28 },
  { day: 29, weekend: true }, { day: 30, weekend: true },
  { day: 31, events: [{ label: "TDS 24Q due · 46", tone: "warning", tip: "TDS 24Q · Q1 FY 2026-27 · 46 clients" }] },
  { day: 1, muted: true }, { day: 2, muted: true }, { day: 3, muted: true }, { day: 4, muted: true },
  { day: 5, weekend: true, muted: true }, { day: 6, weekend: true, muted: true },
];

type ActivityDot = "success" | "danger" | "neutral";
type ActivityItem = {
  dot: ActivityDot;
  icon: React.ReactNode;
  body: React.ReactNode;
  meta: string;
};

const ACTIVITY: ActivityItem[] = [
  {
    dot: "success",
    icon: <CheckCircleIcon size={16} style={{ color: "var(--success)" }} />,
    body: (<><strong style={{ fontWeight: 500 }}>Sundaram Auto Components</strong> filed GSTR-3B for Jul 2026</>),
    meta: "12 min ago · by Priya M.",
  },
  {
    dot: "neutral",
    icon: <UploadIcon size={16} style={{ color: "var(--text-secondary)" }} />,
    body: (<><strong style={{ fontWeight: 500 }}>Bharat Agro Exports</strong> uploaded 14 purchase invoices</>),
    meta: "38 min ago · via client portal",
  },
  {
    dot: "danger",
    icon: <AlertTriangleIcon size={16} style={{ color: "var(--danger)" }} />,
    body: (<>ITC mismatch flagged for <strong style={{ fontWeight: 500 }}>Meghna Logistics</strong> — ₹2,14,900</>),
    meta: "1 hr ago · Niyam AI reconciliation",
  },
  {
    dot: "neutral",
    icon: <MessageSquareIcon size={16} style={{ color: "var(--text-secondary)" }} />,
    body: (<><strong style={{ fontWeight: 500 }}>Rohit S.</strong> commented on Kalyan Steel Traders GSTR-1</>),
    meta: '2 hr ago · "B2B invoice 4412 needs a credit note"',
  },
  {
    dot: "success",
    icon: <CheckCircleIcon size={16} style={{ color: "var(--success)" }} />,
    body: (<><strong style={{ fontWeight: 500 }}>Vertex Pharma Labs</strong> GSTR-2B reconciled — 0 exceptions</>),
    meta: "3 hr ago · by Kavya R.",
  },
  {
    dot: "danger",
    icon: <AlertTriangleIcon size={16} style={{ color: "var(--danger)" }} />,
    body: (<>TDS 24Q for <strong style={{ fontWeight: 500 }}>Ramesh Textiles</strong> crossed its due date</>),
    meta: "5 hr ago · automated watch",
  },
];

type AtRisk = {
  id: string;
  name: string;
  subtitle: string;
  initials: string;
  gstin: string;
  ret: string;
  due: string;
  amount: string;
  status: { label: string; tone: StatusTone };
  ownerName: string;
  ownerInitials: string;
};

const AT_RISK: AtRisk[] = [
  { id: "1", name: "Ramesh Textiles Pvt Ltd", subtitle: "Cotton yarn & grey fabric", initials: "RT",
    gstin: "29AABCR2345M1Z7", ret: "GSTR-3B", due: "20 Jul 2026", amount: "₹18,42,600",
    status: { label: "Overdue · 24d", tone: "danger" }, ownerName: "Priya Menon", ownerInitials: "PM" },
  { id: "2", name: "Bharat Agro Exports LLP", subtitle: "Agri commodity export", initials: "BA",
    gstin: "24AAFCB4417Q1ZL", ret: "TDS 24Q", due: "31 Jul 2026", amount: "₹6,05,400",
    status: { label: "Overdue · 13d", tone: "danger" }, ownerName: "Kavya Rao", ownerInitials: "KR" },
  { id: "3", name: "Vertex Pharma Labs Pvt Ltd", subtitle: "API & formulations", initials: "VP",
    gstin: "36AABCV7729J1Z2", ret: "GSTR-1", due: "11 Aug 2026", amount: "₹27,64,180",
    status: { label: "Blocker", tone: "blocker" }, ownerName: "Priya Menon", ownerInitials: "PM" },
  { id: "4", name: "Sundaram Auto Components Ltd", subtitle: "Auto ancillary manufacturing", initials: "SA",
    gstin: "33AACCS8821K1ZP", ret: "GSTR-1", due: "11 Aug 2026", amount: "₹42,17,850",
    status: { label: "Due in 2 days", tone: "warning" }, ownerName: "Arjun Nair", ownerInitials: "AN" },
  { id: "5", name: "Kalyan Steel Traders", subtitle: "TMT bars & structural steel", initials: "KS",
    gstin: "27AAGFK5518D1ZM", ret: "ROC AOC-4", due: "14 Aug 2026", amount: "₹3,26,750",
    status: { label: "Due in 1 day", tone: "warning" }, ownerName: "Neha Iyer", ownerInitials: "NI" },
  { id: "6", name: "Meghna Logistics Pvt Ltd", subtitle: "Freight & warehousing", initials: "ML",
    gstin: "19AADCM9032H1Z4", ret: "GSTR-3B", due: "20 Aug 2026", amount: "₹11,90,220",
    status: { label: "Blocker", tone: "blocker" }, ownerName: "Rohit Shah", ownerInitials: "RS" },
];

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

const eventToneStyle: Record<EventTone, CSSProperties> = {
  success: { background: "var(--success-soft)", color: "var(--success)" },
  warning: { background: "var(--warning-soft)", color: "var(--warning)" },
  danger: { background: "var(--danger-soft)", color: "var(--danger)" },
  neutral: { background: "var(--row-hover)", color: "var(--text-secondary)" },
};

function EventPill({ tone, tip, children }: { tone: EventTone; tip: string; children: React.ReactNode }) {
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

export default function DashboardPage() {
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
            142 active clients · 3 GSTINs pending registration · FY 2026–27, Q2
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
        <HealthCard />
        <div style={{ gridColumn: "span 7", display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 24 }}>
          <KpiCard label="Upcoming deadlines" value="23" sub="Next 7 days" indicator={<ClockIcon size={16} style={{ color: "var(--text-muted)" }} />} />
          <KpiCard label="Pending filings" value="8" sub="Awaiting client docs" indicator={<Dot color="var(--warning)" />} />
          <KpiCard label="At-risk clients" value="5" sub="Overdue or high-risk" indicator={<Dot color="var(--danger)" />} />
          <KpiCard label="Filed this month" value="47" sub="97% on time" indicator={<Dot color="var(--success)" />} />
        </div>
      </div>

      {/* --- Row 2: calendar + activity --- */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 24, alignItems: "start" }}>
        <CalendarCard />
        <ActivityCard />
      </div>

      {/* --- Row 3: at-risk table --- */}
      <AtRiskSection />
    </div>
  );
}

/* --------------------------------- Row 1 --------------------------------- */

function HealthCard() {
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
        <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, lineHeight: "16px", fontWeight: 500, color: "var(--success)" }}>
          <ArrowUpIcon size={12} />
          +3 vs last month
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 12 }}>
        <span style={{ fontSize: "var(--fs-display)", lineHeight: "var(--lh-display)", fontWeight: "var(--fw-semi)", letterSpacing: "var(--tr-display)", color: "var(--text-primary)" }} className="tabular">87</span>
        <span style={{ fontSize: 18, lineHeight: "28px", fontWeight: "var(--fw-semi)", color: "var(--text-muted)" }}>/100</span>
        <span style={{ marginLeft: 8, padding: "2px 8px", borderRadius: "var(--radius-chip)", background: "var(--success-soft)", color: "var(--success)", fontSize: 12, lineHeight: "16px", fontWeight: 500 }}>Healthy</span>
      </div>
      <div style={{ display: "flex", gap: 3, height: 8, marginTop: "auto" }}>
        <span title="On time · 85 clients" style={{ width: "60%", borderRadius: "var(--radius-pill)", background: "var(--success)" }} />
        <span title="Due within 7 days · 36 clients" style={{ width: "25%", borderRadius: "var(--radius-pill)", background: "var(--warning)" }} />
        <span title="Overdue or blocked · 21 clients" style={{ width: "15%", borderRadius: "var(--radius-pill)", background: "var(--danger)" }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
        <span>Across 142 active clients · Updated 2 min ago</span>
        <span style={{ display: "flex", gap: 12 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Dot color="var(--success)" size={6} />60%</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Dot color="var(--warning)" size={6} />25%</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Dot color="var(--danger)" size={6} />15%</span>
        </span>
      </div>
    </section>
  );
}

function KpiCard({ label, value, sub, indicator }: { label: string; value: string; sub: string; indicator: React.ReactNode }) {
  return (
    <a
      href="#"
      className="v2-kpi v2-focus"
      style={{
        ...CARD,
        boxSizing: "border-box",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        color: "inherit",
        textDecoration: "none",
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
        {value}
      </span>
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>{sub}</span>
    </a>
  );
}

function Dot({ color, size = 8 }: { color: string; size?: number }) {
  return <span style={{ width: size, height: size, borderRadius: "var(--radius-pill)", background: color, display: "inline-block" }} />;
}

/* --------------------------------- Row 2 --------------------------------- */

function CalendarCard() {
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
            <span style={{ minWidth: 104, textAlign: "center", fontSize: 14, fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>August 2026</span>
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 1, background: "var(--border)", borderTop: "1px solid var(--border)" }}>
        {CAL.map((cell, i) => (
          <CalendarCellView key={i} cell={cell} />
        ))}
      </div>
    </section>
  );
}

function CalendarCellView({ cell }: { cell: CalCell }) {
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
        {cell.events?.map((e, i) => <EventPill key={i} tone={e.tone} tip={e.tip}>{e.label}</EventPill>)}
      </div>
    );
  }

  return (
    <div style={{ minHeight: 88, padding: 8, background: bg, display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: dayColor }}>{cell.day}</span>
      {cell.events?.map((e, i) => <EventPill key={i} tone={e.tone} tip={e.tip}>{e.label}</EventPill>)}
      {cell.more != null && (
        <span style={{ fontSize: 11, lineHeight: "16px", color: "var(--text-muted)", paddingLeft: 6, cursor: "default" }}>
          +{cell.more} more
        </span>
      )}
    </div>
  );
}

function ActivityCard() {
  return (
    <section style={{ ...CARD, gridColumn: "span 4", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 24px", borderBottom: "1px solid var(--border)" }}>
        <h2 style={SECTION_TITLE}>Recent Activity</h2>
        <a href="#" className="v2-focus" style={{ fontSize: 12, lineHeight: "16px", fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>View all</a>
      </div>
      <div style={{ position: "relative", padding: "20px 24px 8px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20, borderLeft: "1px solid var(--border)", paddingLeft: 20 }}>
          {ACTIVITY.map((it, i) => (
            <div key={i} style={{ position: "relative", display: "flex", gap: 12 }}>
              <span
                style={{
                  position: "absolute", left: -25, top: 5, width: 9, height: 9,
                  borderRadius: "var(--radius-pill)",
                  background:
                    it.dot === "success" ? "var(--success)" :
                    it.dot === "danger" ? "var(--danger)" : "var(--border-strong)",
                  boxShadow: "0 0 0 3px var(--surface)",
                }}
              />
              <span style={{ flex: "none", marginTop: 2 }}>{it.icon}</span>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 14, lineHeight: "20px", color: "var(--text-primary)" }}>{it.body}</span>
                <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>{it.meta}</span>
              </div>
            </div>
          ))}
        </div>
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

/* --------------------------------- Row 3 --------------------------------- */

function AtRiskSection() {
  return (
    <section style={{ ...CARD, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: "16px 24px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <h2 style={SECTION_TITLE}>At-Risk Clients</h2>
          <span style={{ padding: "2px 8px", borderRadius: "var(--radius-pill)", background: "var(--danger-soft)", color: "var(--danger)", fontSize: 12, lineHeight: "16px", fontWeight: "var(--fw-semi)" }}>
            5
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
          {AT_RISK.map((r) => <AtRiskRow key={r.id} r={r} />)}
        </tbody>
      </table>

      <div style={{ padding: "12px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <a href="#" className="v2-focus" style={{ fontSize: 13, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Load more</a>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Showing 6 of 21 flagged filings · sorted by due date</span>
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

function AtRiskRow({ r }: { r: AtRisk }) {
  return (
    <tr className="v2-row" style={{ height: 56, borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "0 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Monogram initials={r.initials} />
          <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
            <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {r.name}
            </span>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>{r.subtitle}</span>
          </span>
        </div>
      </td>
      <td className="mono" style={{ padding: "0 12px", color: "var(--text-secondary)" }}>{r.gstin}</td>
      <td style={{ padding: "0 12px", fontSize: 14, color: "var(--text-primary)" }}>{r.ret}</td>
      <td style={{ padding: "0 12px", fontSize: 14, color: "var(--text-primary)" }} className="tabular">{r.due}</td>
      <td style={{ padding: "0 12px", textAlign: "right", fontSize: 14, fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }} className="tabular">{r.amount}</td>
      <td style={{ padding: "0 12px" }}>
        <StatusPill tone={r.status.tone}>{r.status.label}</StatusPill>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <MiniAvatar initials={r.ownerInitials} />
          <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>{r.ownerName}</span>
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
