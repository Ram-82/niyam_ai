import type { CSSProperties } from "react";
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
import { StatusPill, type StatusTone } from "@/components/v2/ui/StatusPill";
import { HealthTrack, toneForScore } from "@/components/v2/ui/HealthTrack";

type Client = {
  id: string;
  initials: string;
  name: string;
  subtitle: string;
  gstin: string;
  stateCode: string;
  bizType: string;
  freq: string;
  plan: "Basic" | "Growth" | "Enterprise";
  score: number;
  trend: { label: string; tone: "success" | "warning" | "danger" | "muted" };
  lastFiledDate: string;
  lastFiledRet: string;
  nextDueDate: string;
  nextDueLabel: string;
  nextDueTone: "primary" | "warning" | "danger";
  amountAtRisk: number;
  ownerInitials: string;
  ownerName: string;
  ownerRole: string;
  status: { label: string; tone: StatusTone };
};

const CLIENTS: Client[] = [
  { id: "1", initials: "RT", name: "Ramesh Textiles Pvt Ltd", subtitle: "Karnataka · 5 users · since Apr 2024",
    gstin: "29AAAAA0000A1Z5", stateCode: "KA", bizType: "Regular", freq: "Monthly", plan: "Growth",
    score: 82, trend: { label: "+2 vs last month", tone: "success" },
    lastFiledDate: "12 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 426780, ownerInitials: "PM", ownerName: "Priya M.", ownerRole: "Manager",
    status: { label: "Active", tone: "success" } },
  { id: "2", initials: "CT", name: "CloudMint Technologies Pvt Ltd", subtitle: "Maharashtra · 12 users · since Jan 2023",
    gstin: "27BBBBB0000B1Z2", stateCode: "MH", bizType: "Regular", freq: "Monthly", plan: "Enterprise",
    score: 91, trend: { label: "+3 vs last month", tone: "success" },
    lastFiledDate: "11 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 0, ownerInitials: "AD", ownerName: "Arjun D.", ownerRole: "Partner",
    status: { label: "Active", tone: "success" } },
  { id: "3", initials: "NE", name: "Nova Exports LLP", subtitle: "Gujarat · 3 users · since Sep 2024",
    gstin: "24CCCCC0000C1Z9", stateCode: "GJ", bizType: "SEZ", freq: "Monthly", plan: "Enterprise",
    score: 67, trend: { label: "−6 vs last month", tone: "danger" },
    lastFiledDate: "04 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "11 Aug 2026", nextDueLabel: "GSTR-1 · overdue by 2d", nextDueTone: "danger",
    amountAtRisk: 184220, ownerInitials: "PM", ownerName: "Priya M.", ownerRole: "Manager",
    status: { label: "At risk", tone: "warning" } },
  { id: "4", initials: "ST", name: "Sundar Traders", subtitle: "Tamil Nadu · 2 users · since Jun 2025",
    gstin: "33DDDDD0000D1Z8", stateCode: "TN", bizType: "Composition", freq: "Quarterly", plan: "Basic",
    score: 45, trend: { label: "−11 vs last month", tone: "danger" },
    lastFiledDate: "18 Jul 2026", lastFiledRet: "CMP-08 · Q1 26",
    nextDueDate: "05 Aug 2026", nextDueLabel: "CMP-08 · overdue by 8d", nextDueTone: "danger",
    amountAtRisk: 68540, ownerInitials: "KS", ownerName: "Kavya S.", ownerRole: "Associate",
    status: { label: "Overdue", tone: "danger" } },
  { id: "5", initials: "BS", name: "Bharat Steel Industries Ltd", subtitle: "West Bengal · 18 users · since Mar 2021",
    gstin: "19EEEEE0000E1Z7", stateCode: "WB", bizType: "Regular", freq: "Monthly", plan: "Enterprise",
    score: 88, trend: { label: "no change", tone: "muted" },
    lastFiledDate: "12 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 0, ownerInitials: "AD", ownerName: "Arjun D.", ownerRole: "Partner",
    status: { label: "Active", tone: "success" } },
  { id: "6", initials: "ZC", name: "Zenith Consulting Pvt Ltd", subtitle: "Karnataka · 6 users · since Nov 2023",
    gstin: "29FFFFF0000F1Z1", stateCode: "KA", bizType: "Regular", freq: "Monthly", plan: "Growth",
    score: 78, trend: { label: "+5 vs last month", tone: "success" },
    lastFiledDate: "10 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 92150, ownerInitials: "PM", ownerName: "Priya M.", ownerRole: "Manager",
    status: { label: "Active", tone: "success" } },
  { id: "7", initials: "GH", name: "Green Harvest Foods Pvt Ltd", subtitle: "Punjab · 2 users · since Jul 2026",
    gstin: "03GGGGG0000G1Z0", stateCode: "PB", bizType: "Regular", freq: "Monthly", plan: "Growth",
    score: 72, trend: { label: "+9 vs last month", tone: "success" },
    lastFiledDate: "—", lastFiledRet: "first return pending",
    nextDueDate: "11 Aug 2026", nextDueLabel: "GSTR-1 · overdue by 2d", nextDueTone: "danger",
    amountAtRisk: 0, ownerInitials: "KS", ownerName: "Kavya S.", ownerRole: "Associate",
    status: { label: "Onboarding", tone: "accent" } },
  { id: "8", initials: "ML", name: "Meridian Logistics LLP", subtitle: "Kerala · 4 users · since Feb 2024",
    gstin: "32HHHHH0000H1Z4", stateCode: "KL", bizType: "Regular", freq: "Monthly", plan: "Basic",
    score: 59, trend: { label: "−4 vs last month", tone: "danger" },
    lastFiledDate: "06 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 248900, ownerInitials: "PM", ownerName: "Priya M.", ownerRole: "Manager",
    status: { label: "At risk", tone: "warning" } },
  { id: "9", initials: "AR", name: "Aurora Retail Pvt Ltd", subtitle: "Delhi · 9 users · since Aug 2022",
    gstin: "07JJJJJ0000J1Z6", stateCode: "DL", bizType: "Regular", freq: "Monthly", plan: "Growth",
    score: 94, trend: { label: "+1 vs last month", tone: "success" },
    lastFiledDate: "12 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 0, ownerInitials: "RS", ownerName: "Rohit S.", ownerRole: "Manager",
    status: { label: "Active", tone: "success" } },
  { id: "10", initials: "KC", name: "Kalinga Cement Ltd", subtitle: "Odisha · 15 users · since May 2020",
    gstin: "21KKKKK0000K1Z3", stateCode: "OD", bizType: "Regular", freq: "Monthly", plan: "Enterprise",
    score: 85, trend: { label: "no change", tone: "muted" },
    lastFiledDate: "11 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 112000, ownerInitials: "AD", ownerName: "Arjun D.", ownerRole: "Partner",
    status: { label: "Active", tone: "success" } },
  { id: "11", initials: "VP", name: "Vidya Publishers Pvt Ltd", subtitle: "Rajasthan · 3 users · since Oct 2024",
    gstin: "08LLLLL0000L1Z5", stateCode: "RJ", bizType: "Regular", freq: "Monthly", plan: "Basic",
    score: 38, trend: { label: "−14 vs last month", tone: "danger" },
    lastFiledDate: "28 Jul 2026", lastFiledRet: "GSTR-1 · Jun 26",
    nextDueDate: "11 Aug 2026", nextDueLabel: "GSTR-1 · overdue by 2d", nextDueTone: "danger",
    amountAtRisk: 584300, ownerInitials: "KS", ownerName: "Kavya S.", ownerRole: "Associate",
    status: { label: "Overdue", tone: "danger" } },
  { id: "12", initials: "CR", name: "Coral Reef Exports Pvt Ltd", subtitle: "Goa · 4 users · since Dec 2023",
    gstin: "30MMMMM0000M1ZB", stateCode: "GA", bizType: "SEZ", freq: "Monthly", plan: "Growth",
    score: 81, trend: { label: "+4 vs last month", tone: "success" },
    lastFiledDate: "12 Aug 2026", lastFiledRet: "GSTR-1 · Jul 26",
    nextDueDate: "20 Aug 2026", nextDueLabel: "GSTR-3B · in 7d", nextDueTone: "warning",
    amountAtRisk: 0, ownerInitials: "RS", ownerName: "Rohit S.", ownerRole: "Manager",
    status: { label: "Active", tone: "success" } },
];

const PREVIEW_ID = "1";

const UPCOMING = [
  { badge: "GST-3B", title: "Jul 2026", due: "20 Aug · in 7d", tone: "warning" as const },
  { badge: "TDS", title: "24Q · Q1", due: "31 Aug · in 18d", tone: "muted" as const },
  { badge: "GST-9", title: "FY 25-26", due: "31 Dec · in 140d", tone: "muted" as const },
];

const ACTIVITY = [
  { dot: "success", label: "GSTR-1 filed for Jul 2026", meta: "12 Aug · 11:42 AM" },
  { dot: "neutral", label: "Purchase register uploaded (312 rows)", meta: "10 Aug · 4:18 PM" },
  { dot: "neutral", label: "Ownership transferred to Priya M.", meta: "07 Aug · 10:04 AM" },
  { dot: "success", label: "GSTR-1 filed for Jun 2026", meta: "11 Jul · 3:12 PM" },
] as const;

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
  return (
    <div style={{ display: "flex", alignItems: "stretch", flex: 1, minWidth: 0 }}>
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          background: "var(--bg)",
        }}
      >
        <PageHeader />
        <StatsStrip />
        <FilterRow />
        <TableSection />
      </div>
      <PreviewDrawer />
    </div>
  );
}

/* --------------------------------- Header --------------------------------- */

function PageHeader() {
  return (
    <div
      style={{
        flex: "none",
        boxSizing: "border-box",
        height: 96,
        borderBottom: "1px solid var(--border)",
        padding: "24px 32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 24,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
          Firms · Venkatesh &amp; Co.
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
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
            Clients
          </h1>
          <span
            style={{
              height: 24,
              boxSizing: "border-box",
              padding: "0 10px",
              display: "flex",
              alignItems: "center",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-chip)",
              background: "var(--surface)",
              fontSize: 12,
              fontWeight: "var(--fw-medium)",
              color: "var(--text-secondary)",
            }}
            className="tabular"
          >
            142
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
            height: 32,
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "0 16px",
            border: 0,
            borderRadius: "var(--radius-input)",
            background: "var(--accent)",
            color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`,
            cursor: "pointer",
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
      {icon}
      {children}
    </button>
  );
}

/* --------------------------------- Stats --------------------------------- */

function StatsStrip() {
  return (
    <div style={{ flex: "none", padding: "16px 32px 0" }}>
      <div
        style={{
          ...CARD,
          height: 104,
          boxSizing: "border-box",
          display: "flex",
          alignItems: "stretch",
          overflow: "hidden",
        }}
      >
        <StatCell label="Total clients" value="142" foot={<span style={{ color: "var(--success)" }}>+4 this month</span>} />
        <Divider />
        <StatCell label="Active" value="128" foot={<span style={{ color: "var(--text-muted)" }}>90.1% of book</span>} />
        <Divider />
        <StatCell label="At risk" value="8" foot={<span style={{ color: "var(--warning)" }}>+2 vs last week</span>} />
        <Divider />
        <StatCell label="Overdue" value="5" foot={<span style={{ color: "var(--danger)" }}>3 partners owed</span>} />
        <Divider />
        <div
          style={{
            flex: "none",
            boxSizing: "border-box",
            padding: "16px 24px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", gap: 2, width: 240, height: 6 }}>
            <span style={{ width: "62%", background: "var(--success)", borderRadius: "var(--radius-pill)" }} />
            <span style={{ width: "23%", background: "var(--accent)", borderRadius: "var(--radius-pill)" }} />
            <span style={{ width: "9%", background: "var(--warning)", borderRadius: "var(--radius-pill)" }} />
            <span style={{ width: "6%", background: "var(--danger)", borderRadius: "var(--radius-pill)" }} />
          </div>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>142 clients by health</span>
        </div>
      </div>
    </div>
  );
}

function StatCell({ label, value, foot }: { label: string; value: string; foot: React.ReactNode }) {
  return (
    <div
      style={{
        flex: 1,
        boxSizing: "border-box",
        padding: "16px 24px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 2,
      }}
    >
      <span style={LABEL}>{label}</span>
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
    <div
      style={{
        flex: "none",
        height: 56,
        boxSizing: "border-box",
        marginTop: 32,
        padding: "0 32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 24,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div
          className="v2-search-wrap"
          style={{
            width: 280,
            boxSizing: "border-box",
            height: 32,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 8px 0 10px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
          }}
        >
          <SearchIcon size={16} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search clients, GSTINs, PANs…"
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
          <span
            style={{
              flex: "none",
              padding: "1px 5px",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-chip)",
              fontSize: 11,
              fontWeight: "var(--fw-medium)",
              color: "var(--text-muted)",
            }}
          >
            ⌘F
          </span>
        </div>
        <div style={{ width: 1, height: 20, background: "var(--border)" }} />
        <ActiveChip>Status: Active, At risk</ActiveChip>
        <FilterChip>Plan: All</FilterChip>
        <FilterChip>State: All</FilterChip>
        <FilterChip>Business type: All</FilterChip>
        <FilterChip>Owner: All</FilterChip>
        <FilterChip>Health: All</FilterChip>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--text-secondary)", textDecoration: "none" }}>
          + More filters
        </a>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>
          Clear filters
        </a>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flex: "none" }}>
        <IconButton aria-label="Customize columns" title="Customize columns">
          <SettingsIcon size={16} />
        </IconButton>
        <IconButton aria-label="Export current view" title="Export current view">
          <DownloadIcon size={16} />
        </IconButton>
        <div
          style={{
            height: 32,
            display: "flex",
            alignItems: "stretch",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            overflow: "hidden",
          }}
        >
          <button
            type="button"
            className="v2-focus-inset"
            style={{
              padding: "0 12px",
              border: 0,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              font: `500 12px/16px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            Table
          </button>
          <button
            type="button"
            className="v2-hover-tint v2-focus-inset"
            style={{
              padding: "0 12px",
              border: 0,
              borderLeft: "1px solid var(--border)",
              background: "transparent",
              color: "var(--text-secondary)",
              font: `500 12px/16px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            Board
          </button>
        </div>
      </div>
    </div>
  );
}

function ActiveChip({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        height: 32,
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "0 10px",
        border: 0,
        borderRadius: "var(--radius-input)",
        background: "var(--accent-soft)",
        color: "var(--accent)",
        font: `500 12px/16px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
      <XIcon size={12} />
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

function IconButton({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      {...rest}
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
      {children}
    </button>
  );
}

/* --------------------------------- Table --------------------------------- */

function TableSection() {
  return (
    <div style={{ flex: 1, padding: "0 32px 32px", minHeight: 0 }}>
      <div style={{ ...CARD, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: 40 }} />
            <col style={{ width: 280 }} />
            <col style={{ width: 170 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 120 }} />
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
              <Th>Business type</Th>
              <Th>Plan</Th>
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
            {CLIENTS.map((c, i) => (
              <ClientRow key={c.id} c={c} last={i === CLIENTS.length - 1} />
            ))}
          </tbody>
        </table>
        <Pager />
      </div>
    </div>
  );
}

function Th({
  children,
  align = "left",
  sortable,
  active,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  sortable?: boolean;
  active?: boolean;
}) {
  const base: CSSProperties = {
    padding: "0 12px",
    textAlign: align,
    font: `500 11px/16px var(--font-sans-v2)`,
    letterSpacing: "var(--tr-label)",
    textTransform: "uppercase",
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

function ClientRow({ c, last }: { c: Client; last: boolean }) {
  const isPreview = c.id === PREVIEW_ID;
  const rowStyle: CSSProperties = isPreview
    ? {
        height: 56,
        borderBottom: last ? undefined : "1px solid var(--border)",
        background: "var(--row-hover-accent)",
        boxShadow: "inset 2px 0 0 var(--accent)",
      }
    : {
        height: 56,
        borderBottom: last ? undefined : "1px solid var(--border)",
      };
  const trendColor =
    c.trend.tone === "success" ? "var(--success)" :
    c.trend.tone === "danger" ? "var(--danger)" :
    c.trend.tone === "warning" ? "var(--warning)" : "var(--text-muted)";

  const nextDueColor =
    c.nextDueTone === "warning" ? "var(--warning)" :
    c.nextDueTone === "danger" ? "var(--danger)" : "var(--text-primary)";

  const scoreTone = toneForScore(c.score);
  const scoreColor =
    scoreTone === "success" ? "var(--success)" :
    scoreTone === "warning" ? "var(--warning)" : "var(--danger)";

  const amountRender = amountAtRisk(c.amountAtRisk);

  const planStyle: CSSProperties =
    c.plan === "Enterprise"
      ? { background: "var(--accent-soft)", color: "var(--accent)", border: "none" }
      : { background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)" };

  return (
    <tr className={isPreview ? "" : "v2-row"} style={rowStyle}>
      <td style={{ padding: 0, textAlign: "center" }}>
        <input type="checkbox" aria-label={`Select ${c.name}`} style={{ width: 14, height: 14, accentColor: "var(--accent)", cursor: "pointer" }} />
      </td>
      <td style={{ padding: "0 12px 0 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Monogram initials={c.initials} />
          <span style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.name}
            </span>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.subtitle}
            </span>
          </span>
        </div>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span className="mono" style={{ color: "var(--text-secondary)" }}>{c.gstin}</span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{c.stateCode}</span>
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-primary)" }}>{c.bizType}</span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{c.freq}</span>
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span
          style={{
            height: 24,
            boxSizing: "border-box",
            display: "inline-flex",
            alignItems: "center",
            padding: "0 8px",
            borderRadius: "var(--radius-chip)",
            fontSize: 11,
            fontWeight: "var(--fw-medium)",
            ...planStyle,
          }}
        >
          {c.plan}
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <HealthTrack score={c.score} />
            <span className="tabular" style={{ fontSize: 13, fontWeight: "var(--fw-medium)", color: scoreColor }}>{c.score}</span>
          </span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: trendColor }}>{c.trend.label}</span>
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span className="tabular" style={{ fontSize: 13, lineHeight: "18px", color: c.lastFiledDate === "—" ? "var(--text-muted)" : "var(--text-primary)" }}>
            {c.lastFiledDate}
          </span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{c.lastFiledRet}</span>
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", flexDirection: "column" }}>
          <span className="tabular" style={{ fontSize: 13, lineHeight: "18px", color: nextDueColor }}>{c.nextDueDate}</span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{c.nextDueLabel}</span>
        </span>
      </td>
      <td className="tabular" style={{ padding: "0 12px", textAlign: "right", fontSize: 13, fontWeight: amountRender.weight, color: amountRender.color }}>
        {amountRender.text}
      </td>
      <td style={{ padding: "0 12px" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <MiniAvatar initials={c.ownerInitials} />
          <span style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 14, lineHeight: "16px", color: "var(--text-primary)" }}>{c.ownerName}</span>
            <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{c.ownerRole}</span>
          </span>
        </span>
      </td>
      <td style={{ padding: "0 12px" }}>
        <StatusPill tone={c.status.tone}>{c.status.label}</StatusPill>
      </td>
      <td style={{ padding: "0 8px", textAlign: "right" }}>
        <button
          type="button"
          aria-label="Row actions"
          className="v2-row-actions v2-focus"
          style={{
            width: 28,
            height: 28,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            border: 0,
            borderRadius: "var(--radius-chip)",
            background: "transparent",
            color: "var(--text-secondary)",
            cursor: "pointer",
          }}
        >
          <MoreHorizontalIcon size={16} />
        </button>
      </td>
    </tr>
  );
}

function amountAtRisk(n: number): { text: string; color: string; weight: number } {
  if (n === 0) return { text: "—", color: "var(--text-muted)", weight: 400 };
  const inr = new Intl.NumberFormat("en-IN").format(n);
  if (n >= 500000) return { text: `₹${inr}`, color: "var(--danger)", weight: 500 };
  if (n >= 100000) return { text: `₹${inr}`, color: "var(--warning)", weight: 500 };
  return { text: `₹${inr}`, color: "var(--text-primary)", weight: 400 };
}

function Pager() {
  return (
    <div
      style={{
        height: 56,
        boxSizing: "border-box",
        borderTop: "1px solid var(--border)",
        padding: "0 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 24,
      }}
    >
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }} className="tabular">
        1–12 of 142 clients
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <PageBtn>‹ Previous</PageBtn>
        <PageNum active>1</PageNum>
        <PageNum>2</PageNum>
        <PageNum>3</PageNum>
        <span style={{ width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "var(--text-muted)" }}>…</span>
        <PageNum>12</PageNum>
        <PageBtn>Next ›</PageBtn>
      </div>
      <button
        type="button"
        className="v2-hover-tint v2-focus"
        style={{
          height: 32,
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "0 10px",
          border: 0,
          borderRadius: "var(--radius-input)",
          background: "transparent",
          color: "var(--text-secondary)",
          font: `500 12px/16px var(--font-sans-v2)`,
          cursor: "pointer",
        }}
      >
        Rows: 12
        <ChevronDownIcon size={12} />
      </button>
    </div>
  );
}

function PageBtn({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-hover-tint v2-focus"
      style={{
        height: 32,
        padding: "0 10px",
        border: 0,
        borderRadius: "var(--radius-input)",
        background: "transparent",
        font: `500 12px/16px var(--font-sans-v2)`,
        color: "var(--text-secondary)",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function PageNum({ children, active }: { children: React.ReactNode; active?: boolean }) {
  return (
    <button
      type="button"
      className={active ? "v2-focus" : "v2-hover-tint v2-focus"}
      style={{
        width: 32,
        height: 32,
        border: 0,
        borderRadius: "var(--radius-input)",
        background: active ? "var(--accent-soft)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        font: `500 12px/16px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

/* --------------------------------- Drawer --------------------------------- */

function PreviewDrawer() {
  const preview = CLIENTS.find((c) => c.id === PREVIEW_ID)!;
  return (
    <aside
      style={{
        width: 400,
        flex: "none",
        boxSizing: "border-box",
        background: "var(--surface)",
        borderLeft: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div
        style={{
          height: 72,
          flex: "none",
          boxSizing: "border-box",
          padding: "16px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span
          style={{
            width: 40,
            height: 40,
            flex: "none",
            borderRadius: 8,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            fontWeight: "var(--fw-semi)",
          }}
        >
          {preview.initials}
        </span>
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 18, lineHeight: "22px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {preview.name}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ padding: "2px 6px", borderRadius: "var(--radius-chip)", background: "var(--success-soft)", color: "var(--success)", fontSize: 11, lineHeight: "14px", fontWeight: "var(--fw-medium)" }}>
              Active
            </span>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>Client since Apr 2024</span>
          </span>
        </span>
        <button
          type="button"
          aria-label="Close preview"
          className="v2-hover-tint v2-focus"
          style={{
            width: 24,
            height: 24,
            flex: "none",
            alignSelf: "flex-start",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: 0,
            borderRadius: "var(--radius-chip)",
            background: "transparent",
            color: "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          <XIcon size={14} />
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        <div
          style={{
            padding: "16px 20px",
            background: "var(--bg)",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "8px 12px",
            fontSize: 12,
            lineHeight: "16px",
          }}
        >
          <MetaKey>GSTIN</MetaKey><MetaVal mono>29AAAAA0000A1Z5</MetaVal>
          <MetaKey>PAN</MetaKey><MetaVal mono>AAAPT1234A</MetaVal>
          <MetaKey>State</MetaKey><MetaVal>Karnataka</MetaVal>
          <MetaKey>Business type</MetaKey><MetaVal>Regular · Monthly</MetaVal>
          <MetaKey>Plan</MetaKey><MetaVal>Growth</MetaVal>
          <MetaKey>Filing freq.</MetaKey><MetaVal>Monthly</MetaVal>
        </div>

        <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
          <ComplianceCard />
          <UpcomingCard />
          <ActivityCard />
          <KeyContactCard />
        </div>
      </div>

      <div
        style={{
          height: 120,
          flex: "none",
          boxSizing: "border-box",
          borderTop: "1px solid var(--border)",
          padding: "16px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <button
          type="button"
          className="v2-btn-primary v2-focus"
          style={{
            flex: "none",
            height: 40,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            border: 0,
            borderRadius: "var(--radius-input)",
            background: "var(--accent)",
            color: "var(--on-accent)",
            font: `500 14px/20px var(--font-sans-v2)`,
            cursor: "pointer",
          }}
        >
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
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      style={{
        flex: 1,
        height: 32,
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-input)",
        background: "transparent",
        font: `500 13px/20px var(--font-sans-v2)`,
        color: "var(--text-primary)",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function ComplianceCard() {
  return (
    <div style={{ boxSizing: "border-box", padding: 16, border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ height: 24, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Compliance health</span>
        <span className="tabular" style={{ fontSize: 14, fontWeight: "var(--fw-semi)", color: "var(--success)" }}>82/100</span>
      </div>
      <div style={{ display: "flex", gap: 2, height: 8 }}>
        <span style={{ width: "70%", background: "var(--success)", borderRadius: "var(--radius-pill)" }} />
        <span style={{ width: "22%", background: "var(--warning)", borderRadius: "var(--radius-pill)" }} />
        <span style={{ width: "8%", background: "var(--danger)", borderRadius: "var(--radius-pill)" }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 11, lineHeight: "16px", color: "var(--text-muted)" }}>
        <LegendDot color="var(--success)">Compliant</LegendDot>
        <LegendDot color="var(--warning)">At risk</LegendDot>
        <LegendDot color="var(--danger)">Overdue</LegendDot>
      </div>
      <div style={{ height: 1, background: "var(--border)" }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        <KpiMini label="This month" value="3 filings" foot={<span style={{ color: "var(--success)" }}>All on time</span>} />
        <KpiMini label="Blockers" value="1" foot={<span style={{ color: "var(--text-muted)" }}>Awaiting docs</span>} />
        <KpiMini label="Score trend" value={<span style={{ color: "var(--success)" }}>+2</span>} foot={<span style={{ color: "var(--text-muted)" }}>vs last month</span>} />
      </div>
    </div>
  );
}

function LegendDot({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: 6, height: 6, borderRadius: "var(--radius-pill)", background: color }} />
      {children}
    </span>
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

function UpcomingCard() {
  return (
    <div style={{ boxSizing: "border-box", border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)", overflow: "hidden" }}>
      <div style={{ padding: "16px 16px 12px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Upcoming</span>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>View all</a>
      </div>
      {UPCOMING.map((u, i) => (
        <div
          key={i}
          style={{
            height: 48,
            boxSizing: "border-box",
            padding: "0 16px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span
            style={{
              flex: "none",
              height: 20,
              padding: "0 6px",
              display: "flex",
              alignItems: "center",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--text-secondary)",
              fontSize: 10,
              fontWeight: "var(--fw-semi)",
              letterSpacing: "var(--tr-label)",
            }}
          >
            {u.badge}
          </span>
          <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {u.title}
          </span>
          {u.tone === "warning" ? (
            <span style={{ flex: "none", padding: "2px 8px", borderRadius: "var(--radius-chip)", background: "var(--warning-soft)", color: "var(--warning)", fontSize: 11, lineHeight: "16px", fontWeight: "var(--fw-medium)" }}>
              {u.due}
            </span>
          ) : (
            <span className="tabular" style={{ flex: "none", fontSize: 11, color: "var(--text-muted)" }}>{u.due}</span>
          )}
        </div>
      ))}
    </div>
  );
}

function ActivityCard() {
  return (
    <div style={{ boxSizing: "border-box", padding: 16, border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)", display: "flex", flexDirection: "column", gap: 12 }}>
      <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Recent activity</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 16, borderLeft: "1px solid var(--border)", paddingLeft: 16 }}>
        {ACTIVITY.map((a, i) => (
          <div key={i} style={{ position: "relative", display: "flex", flexDirection: "column", gap: 2 }}>
            <span
              style={{
                position: "absolute",
                left: -20,
                top: 5,
                width: 8,
                height: 8,
                borderRadius: "var(--radius-pill)",
                background: a.dot === "success" ? "var(--success)" : "var(--border-strong)",
                boxShadow: "0 0 0 3px var(--surface)",
              }}
            />
            <span style={{ fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>{a.label}</span>
            <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{a.meta}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function KeyContactCard() {
  return (
    <div style={{ boxSizing: "border-box", padding: 16, border: "1px solid var(--border)", borderRadius: "var(--radius-app-card)", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          style={{
            width: 32,
            height: 32,
            flex: "none",
            borderRadius: "var(--radius-pill)",
            background: "var(--row-hover)",
            color: "var(--text-secondary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            fontWeight: "var(--fw-semi)",
          }}
        >
          SR
        </span>
        <span style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>Suresh Ramesh</span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>Director · key contact</span>
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <ContactChip>
          <PhoneSvg />
          +91 98450 12345
        </ContactChip>
        <ContactChip>
          <MailSvg />
          finance@ramesh…
        </ContactChip>
        <ContactChip tone="success">
          <MessageSvg />
          WhatsApp connected
        </ContactChip>
      </div>
    </div>
  );
}

function ContactChip({ children, tone }: { children: React.ReactNode; tone?: "success" }) {
  return (
    <span
      style={{
        height: 24,
        boxSizing: "border-box",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "0 8px",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-chip)",
        fontSize: 11,
        color: tone === "success" ? "var(--success)" : "var(--text-secondary)",
      }}
    >
      {children}
    </span>
  );
}

function PhoneSvg() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3h3l2 5-2.5 1.5a12 12 0 0 0 5 5L15 12l5 2v3a2 2 0 0 1-2.2 2A17 17 0 0 1 4 5.2 2 2 0 0 1 6 3" />
    </svg>
  );
}

function MailSvg() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  );
}

function MessageSvg() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.5 8.5 0 0 1-12.5 7.5L3 21l2-5.5A8.5 8.5 0 1 1 21 11.5" />
    </svg>
  );
}
