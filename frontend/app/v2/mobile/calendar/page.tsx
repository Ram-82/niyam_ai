"use client";

import { ChevronLeftIcon, ChevronDownIcon, FilterIcon, SearchIcon } from "@/components/v2/icons";

/* --- iOS status bar icons ------------------------------------------------ */

const SignalSvg = () => (
  <svg width={16} height={12} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2.5} strokeLinecap="round">
    <path d="M3 20h.01M8.5 20v-4M14 20v-9M19.5 20V5" />
  </svg>
);
const WifiSvg = () => (
  <svg width={16} height={12} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round">
    <path d="M2 9a15 15 0 0 1 20 0" />
    <path d="M5.5 12.5a10 10 0 0 1 13 0" />
    <path d="M9 16a5 5 0 0 1 6 0" />
    <path d="M12 19.5h.01" />
  </svg>
);
const BatterySvg = () => (
  <svg width={28} height={14} viewBox="0 0 28 14" fill="none"
    stroke="currentColor" strokeWidth={1.5}>
    <rect x={1} y={1} width={22} height={12} rx={3} />
    <rect x={3} y={3} width={16} height={8} rx={1.5} fill="currentColor" stroke="none" />
    <path d="M25 5v4" strokeLinecap="round" />
  </svg>
);

/* --- tab bar icons ------------------------------------------------------- */

const DashSvg = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <rect x={3} y={3} width={7} height={9} rx={1.5} />
    <rect x={14} y={3} width={7} height={5} rx={1.5} />
    <rect x={14} y={12} width={7} height={9} rx={1.5} />
    <rect x={3} y={16} width={7} height={5} rx={1.5} />
  </svg>
);
const CalSvg = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <rect x={3} y={4} width={18} height={17} rx={2} />
    <path d="M16 2v4M8 2v4M3 10h18" />
  </svg>
);
const FilingsSvg = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" /><path d="m9 15 2 2 4-4" />
  </svg>
);
const AiSvg = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <path d="m12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    <path d="m18.5 15.5.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" />
  </svg>
);
const MenuSvg = () => (
  <svg width={22} height={22} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round">
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);
const PlusSvg = () => (
  <svg width={24} height={24} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round">
    <path d="M12 5v14M5 12h14" />
  </svg>
);

/* --- data ---------------------------------------------------------------- */

type Ev = {
  ret: string; title: string; sub: string;
  status: string;
  statusBg: string; statusFg: string; statusBorder?: string;
  bar: string;
  time: string;
};

const OVERDUE: Ev[] = [
  { ret: "CMP", title: "CMP-08 · Q1 · 2 clients",
    sub: "Sundar Traders + 1",
    status: "Overdue", statusBg: "var(--danger-soft)", statusFg: "var(--danger)",
    bar: "var(--danger)", time: "8d late" },
  { ret: "AOC", title: "AOC-4 · FY 25-26 · 1 client",
    sub: "Meridian Logistics LLP",
    status: "Overdue", statusBg: "var(--danger-soft)", statusFg: "var(--danger)",
    bar: "var(--danger)", time: "7d late" },
];

const TODAY: Ev[] = [
  { ret: "GST-3B", title: "Ramesh Textiles Pvt Ltd",
    sub: "Arjun D. · ₹4,26,780",
    status: "In prog", statusBg: "var(--accent-soft)", statusFg: "var(--accent)",
    bar: "var(--accent)", time: "due 20 Aug" },
  { ret: "DIR", title: "DIR-3 KYC · CloudMint",
    sub: "Prep task · Priya M.",
    status: "Prep",
    statusBg: "transparent", statusFg: "var(--text-secondary)",
    statusBorder: "1px solid var(--border)",
    bar: "var(--border-strong)", time: "in 3d" },
];

const TOMORROW: Ev[] = [
  { ret: "GST-1", title: "Late filing · Nova Exports",
    sub: "₹0 penalty exposure",
    status: "Due tmw", statusBg: "var(--warning-soft)", statusFg: "var(--warning)",
    bar: "var(--warning)", time: "1d" },
];

const FRI: Ev[] = [
  { ret: "PF", title: "PF & ESI · 62 clients",
    sub: "Batch task · Team",
    status: "Batch", statusBg: "var(--warning-soft)", statusFg: "var(--warning)",
    bar: "var(--warning)", time: "in 2d" },
  { ret: "TDS", title: "Jul late fee · 12 clients",
    sub: "Escalated · Priya M.",
    status: "Escal.", statusBg: "var(--warning-soft)", statusFg: "var(--warning)",
    bar: "var(--warning)", time: "in 2d" },
];

const MON: Ev[] = [
  { ret: "GST-3B", title: "QRMP payment · 8 clients",
    sub: "₹6,40,000",
    status: "Due", statusBg: "var(--warning-soft)", statusFg: "var(--warning)",
    bar: "var(--warning)", time: "in 4d" },
];

const WED: Ev[] = [
  { ret: "GST-3B", title: "Monthly · 84 clients",
    sub: "₹2.14 Cr · Team",
    status: "Blocker", statusBg: "var(--danger-soft)", statusFg: "var(--danger)",
    bar: "var(--danger)", time: "in 7d" },
];

/* --- mini calendar data (Sun 9 – Sat 15 Aug 2026) ------------------------ */

type Day = { n: number; dim?: boolean; today?: boolean; dot: string };
const WEEK: Day[] = [
  { n: 9,  dim: true,  dot: "var(--border-strong)" },
  { n: 10,             dot: "var(--warning)" },
  { n: 11,             dot: "var(--danger)" },
  { n: 12,             dot: "var(--success)" },
  { n: 13, today: true, dot: "var(--warning)" },
  { n: 14,             dot: "var(--warning)" },
  { n: 15, dim: true,  dot: "var(--warning)" },
];

/* --- pieces -------------------------------------------------------------- */

function StatusBar() {
  return (
    <div style={{
      height: 47, flex: "none", padding: "0 24px",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      background: "var(--surface)", color: "var(--text-primary)",
    }}>
      <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em" }}>9:41</div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <SignalSvg /><WifiSvg /><BatterySvg />
      </div>
    </div>
  );
}

function TopNav() {
  return (
    <div style={{
      height: 56, flex: "none", padding: "0 8px",
      background: "var(--surface)", borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: 4,
    }}>
      <button aria-label="Back" style={{
        width: 40, height: 40, border: "none", background: "transparent",
        borderRadius: 10, cursor: "pointer", color: "var(--text-secondary)",
        display: "grid", placeItems: "center", flex: "none",
      }}>
        <ChevronLeftIcon size={22} />
      </button>
      <button style={{
        flex: 1, minWidth: 0, height: 44,
        border: "none", background: "transparent", cursor: "pointer",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{
            fontSize: 15, fontWeight: 600, color: "var(--text-primary)",
          }}>August 2026</span>
          <span style={{ color: "var(--text-muted)" }}><ChevronDownIcon size={14} /></span>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
          23 deadlines · 5 overdue
        </div>
      </button>
      <button aria-label="Filter" style={{
        width: 40, height: 40, border: "none", background: "transparent",
        borderRadius: 10, cursor: "pointer", color: "var(--text-secondary)",
        display: "grid", placeItems: "center", flex: "none",
      }}>
        <FilterIcon size={20} />
      </button>
      <button aria-label="Search" style={{
        width: 40, height: 40, border: "none", background: "transparent",
        borderRadius: 10, cursor: "pointer", color: "var(--text-secondary)",
        display: "grid", placeItems: "center", flex: "none",
      }}>
        <SearchIcon size={20} />
      </button>
    </div>
  );
}

function ViewToggle() {
  const opts = ["Agenda", "Month", "Week"] as const;
  const active = "Agenda";
  return (
    <div style={{
      margin: "12px 16px 0",
      display: "inline-flex", height: 32,
      border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden",
      background: "var(--surface)",
    }}>
      {opts.map((o, i) => (
        <button key={o} style={{
          padding: "0 14px", fontSize: 12, fontWeight: 500,
          border: "none", cursor: "pointer",
          borderLeft: i === 0 ? "none" : "1px solid var(--border)",
          background: o === active ? "var(--accent-soft)" : "transparent",
          color: o === active ? "var(--accent)" : "var(--text-secondary)",
        }}>{o}</button>
      ))}
    </div>
  );
}

function MiniWeek() {
  const heads = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];
  return (
    <div style={{
      margin: "12px 16px 0",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, padding: "8px 4px",
    }}>
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(7, 1fr)",
        alignItems: "center", height: 24,
      }}>
        {heads.map(h => (
          <div key={h} style={{
            textAlign: "center", fontSize: 10, fontWeight: 500,
            letterSpacing: "0.06em", color: "var(--text-muted)",
          }}>{h}</div>
        ))}
      </div>
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(7, 1fr)",
        alignItems: "center", height: 48,
      }}>
        {WEEK.map(d => (
          <div key={d.n} style={{
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 4,
            opacity: d.dim ? 0.5 : 1,
          }}>
            {d.today ? (
              <div style={{
                width: 30, height: 30, borderRadius: 999,
                background: "var(--accent)", color: "#fff",
                display: "grid", placeItems: "center",
                fontSize: 13, fontWeight: 600,
              }}>{d.n}</div>
            ) : (
              <div style={{
                fontSize: 13, fontWeight: 500, color: "var(--text-primary)",
              }}>{d.n}</div>
            )}
            <div style={{
              width: 16, height: 2, borderRadius: 999, background: d.dot,
            }} />
          </div>
        ))}
      </div>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "4px 12px 0",
      }}>
        <button style={{
          border: "none", background: "transparent", cursor: "pointer",
          fontSize: 12, color: "var(--text-secondary)",
        }}>‹ Prev week</button>
        <button style={{
          border: "none", background: "transparent", cursor: "pointer",
          fontSize: 12, fontWeight: 500, color: "var(--accent)",
        }}>Today</button>
        <button style={{
          border: "none", background: "transparent", cursor: "pointer",
          fontSize: 12, color: "var(--text-secondary)",
        }}>Next week ›</button>
      </div>
    </div>
  );
}

function SectionHeader({ label, count, tone = "neutral", accentWord }: {
  label: string; count: string;
  tone?: "neutral" | "danger";
  accentWord?: string;
}) {
  const bg = tone === "danger" ? "#FDF2F2" : "var(--row-hover)";
  const fg = tone === "danger" ? "var(--danger)" : "var(--text-muted)";
  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 1,
      height: 40, padding: "0 16px",
      background: bg, color: fg,
      display: "flex", alignItems: "center", justifyContent: "space-between",
      fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
      textTransform: "uppercase",
    }}>
      <span>
        {accentWord && (
          <span style={{ color: "var(--accent)" }}>{accentWord} </span>
        )}
        {label}
      </span>
      <span style={{ fontSize: 11, textTransform: "none", letterSpacing: 0 }}>{count}</span>
    </div>
  );
}

function EventCard({ ev }: { ev: Ev }) {
  return (
    <div style={{
      minHeight: 76, padding: "12px 14px",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderLeft: `3px solid ${ev.bar}`,
      borderRadius: 12,
      display: "flex", flexDirection: "column", gap: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          height: 20, padding: "0 6px",
          border: "1px solid var(--border)", borderRadius: 6,
          background: "var(--surface)",
          fontSize: 10, fontWeight: 600, color: "var(--text-secondary)",
          display: "inline-flex", alignItems: "center", flex: "none",
        }}>{ev.ret}</span>
        <span style={{
          flex: 1, minWidth: 0,
          fontSize: 15, fontWeight: 500, color: "var(--text-primary)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{ev.title}</span>
        <span style={{
          height: 18, padding: "0 8px", flex: "none",
          background: ev.statusBg, color: ev.statusFg,
          border: ev.statusBorder ?? "none",
          borderRadius: 999,
          display: "inline-flex", alignItems: "center",
          fontSize: 11, fontWeight: 500,
        }}>{ev.status}</span>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{ev.sub}</div>
      <div style={{ alignSelf: "flex-end", fontSize: 11, color: "var(--text-muted)" }}>
        {ev.time}
      </div>
    </div>
  );
}

function Group({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: "8px 16px 12px",
      display: "flex", flexDirection: "column", gap: 8,
    }}>{children}</div>
  );
}

function TabBar() {
  const tabs = [
    { key: "dashboard", label: "Dashboard", icon: <DashSvg /> },
    { key: "calendar",  label: "Calendar",  icon: <CalSvg />, active: true },
    { key: "filings",   label: "Filings",   icon: <FilingsSvg /> },
    { key: "ai",        label: "AI",        icon: <AiSvg /> },
    { key: "more",      label: "More",      icon: <MenuSvg /> },
  ];
  return (
    <div style={{
      height: 90, paddingBottom: 34, flex: "none",
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      display: "flex", alignItems: "stretch",
    }}>
      {tabs.map(t => (
        <a key={t.key} href="#" style={{
          flex: 1, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 4,
          textDecoration: "none",
          color: t.active ? "var(--accent)" : "var(--text-muted)",
        }}>
          {t.icon}
          <span style={{ fontSize: 10, fontWeight: 500 }}>{t.label}</span>
        </a>
      ))}
    </div>
  );
}

/* --- page ---------------------------------------------------------------- */

export default function MobileCalendarPage() {
  return (
    <div style={{
      minHeight: "100vh", padding: 40,
      background: "var(--bg)",
      display: "grid", placeItems: "start center",
    }}>
      <div style={{
        width: 390, height: 844, position: "relative",
        background: "var(--bg)",
        border: "1px solid var(--border)",
        borderRadius: 44, overflow: "hidden",
        display: "flex", flexDirection: "column",
        boxShadow: "0 24px 64px rgba(15,23,42,0.12), 0 8px 24px rgba(15,23,42,0.06)",
      }}>
        <StatusBar />
        <TopNav />

        {/* scroll area */}
        <div style={{
          flex: 1, minHeight: 0, overflowY: "auto",
          paddingBottom: 96,
        }}>
          <ViewToggle />
          <MiniWeek />

          <div style={{ marginTop: 16 }}>
            <SectionHeader label="Overdue" count="2 overdue" tone="danger" />
            <Group>
              {OVERDUE.map((e, i) => <EventCard key={i} ev={e} />)}
            </Group>

            <SectionHeader label="Wed 13 Aug" count="2 deadlines" accentWord="Today ·" />
            <Group>
              {TODAY.map((e, i) => <EventCard key={i} ev={e} />)}
            </Group>

            <SectionHeader label="Tomorrow · Thu 14 Aug" count="1 deadline" />
            <Group>
              {TOMORROW.map((e, i) => <EventCard key={i} ev={e} />)}
            </Group>

            <SectionHeader label="Fri 15 Aug" count="2 deadlines" />
            <Group>
              {FRI.map((e, i) => <EventCard key={i} ev={e} />)}
            </Group>

            <SectionHeader label="Mon 17 Aug" count="1 deadline" />
            <Group>
              {MON.map((e, i) => <EventCard key={i} ev={e} />)}
            </Group>

            <SectionHeader label="Wed 20 Aug" count="5 deadlines" />
            <Group>
              {WED.map((e, i) => <EventCard key={i} ev={e} />)}
            </Group>
          </div>
        </div>

        <button aria-label="Add reminder" style={{
          position: "absolute", right: 24, bottom: 114, zIndex: 4,
          width: 56, height: 56, borderRadius: 999,
          background: "var(--accent)", color: "#fff", border: "none",
          cursor: "pointer",
          boxShadow: "0 4px 12px rgba(15,23,42,0.16), 0 12px 32px rgba(36,71,242,0.24)",
          display: "grid", placeItems: "center",
        }}>
          <PlusSvg />
        </button>

        <TabBar />
      </div>
    </div>
  );
}
