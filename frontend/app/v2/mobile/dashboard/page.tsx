"use client";

import { BellIcon, ChevronRightIcon } from "@/components/v2/icons";

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
const CalendarSvg = () => (
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
    <path d="M14 2v6h6" />
    <path d="m9 15 2 2 4-4" />
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

/* --- small KPI icons ----------------------------------------------------- */

const ClockSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={12} cy={12} r={9} /><path d="M12 7v5.2l3 1.8" />
  </svg>
);
const DocSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h6" />
    <path d="M14 2v6h6" />
    <circle cx={17} cy={17} r={4} />
  </svg>
);
const AlertSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.3 4 2.6 17.5A1.6 1.6 0 0 0 4 20h16a1.6 1.6 0 0 0 1.4-2.5L13.7 4a1.6 1.6 0 0 0-2.8 0" />
    <path d="M12 9.5v4M12 17h.01" />
  </svg>
);
const OkSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={12} cy={12} r={9} /><path d="m8.5 12.5 2.4 2.4 4.6-5.2" />
  </svg>
);
const PlusSvg = () => (
  <svg width={24} height={24} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round">
    <path d="M12 5v14M5 12h14" />
  </svg>
);

/* --- data ---------------------------------------------------------------- */

const KPIS = [
  { icon: <ClockSvg />, iconBg: "var(--warning-soft)", iconFg: "var(--warning)",
    period: "Next 7d",   value: "23", desc: "deadlines" },
  { icon: <DocSvg />, iconBg: "var(--accent-soft)", iconFg: "var(--accent)",
    period: "Pending",   value: "8",  desc: "awaiting docs" },
  { icon: <AlertSvg />, iconBg: "var(--danger-soft)", iconFg: "var(--danger)",
    period: "At risk",   value: "5",  desc: "overdue or high-risk" },
  { icon: <OkSvg />, iconBg: "var(--success-soft)", iconFg: "var(--success)",
    period: "This month", value: "47", desc: "97% on time" },
];

type Filing = {
  ret: string; title: string; sub: string;
  status: string; statusBg: string; statusFg: string; barTone: string;
};
const FILINGS: Filing[] = [
  { ret: "GST-1",  title: "GST-1 · Nova Exports LLP",
    sub: "Due tomorrow · ₹1,84,220 at risk",
    status: "Tomorrow", statusBg: "var(--warning-soft)", statusFg: "var(--warning)",
    barTone: "var(--warning)" },
  { ret: "GST-3B", title: "GST-3B · Ramesh Textiles",
    sub: "In progress · Arjun D. · ₹4,26,780",
    status: "In prog", statusBg: "var(--accent-soft)", statusFg: "var(--accent)",
    barTone: "var(--accent)" },
  { ret: "DIR",    title: "DIR-3 KYC · CloudMint",
    sub: "Prep needed · 4 directors · Priya M.",
    status: "3d", statusBg: "var(--warning-soft)", statusFg: "var(--warning)",
    barTone: "var(--warning)" },
];

type Client = {
  init: string; avBg: string; avFg: string;
  name: string; sub: string;
  status: string; statusBg: string; statusFg: string;
};
const AT_RISK: Client[] = [
  { init: "ST", avBg: "var(--accent-soft)", avFg: "var(--accent)",
    name: "Sundar Traders", sub: "Overdue 8 days · ₹68,540",
    status: "Overdue", statusBg: "var(--danger-soft)", statusFg: "var(--danger)" },
  { init: "VP", avBg: "var(--warning-soft)", avFg: "var(--warning)",
    name: "Vidya Publishers Pvt Ltd", sub: "Overdue 2 days · ₹5,84,300",
    status: "Overdue", statusBg: "var(--danger-soft)", statusFg: "var(--danger)" },
  { init: "ML", avBg: "var(--success-soft)", avFg: "var(--success)",
    name: "Meridian Logistics LLP", sub: "Due today · ₹2,48,900",
    status: "Due today", statusBg: "var(--warning-soft)", statusFg: "var(--warning)" },
];

const ACTIVITY = [
  { dot: "var(--success)", msg: "Ramesh Textiles filed GSTR-1 for Jul 2026", meta: "12m ago · Priya M." },
  { dot: "var(--accent)",  msg: "New at-risk client flagged: Sundar Traders", meta: "1h ago · System" },
  { dot: "var(--warning)", msg: "Kavya S. resolved 4 validation errors",     meta: "2h ago" },
];

/* --- components ---------------------------------------------------------- */

function StatusBar() {
  return (
    <div style={{
      height: 47, flex: "none",
      padding: "0 24px",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      background: "var(--surface)",
      color: "var(--text-primary)",
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
      height: 56, flex: "none", padding: "0 16px",
      background: "var(--surface)",
      borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: 12,
    }}>
      <button aria-label="Switch workspace" style={{
        width: 32, height: 32, borderRadius: 8,
        background: "var(--accent-soft)", color: "var(--accent)",
        border: "none", cursor: "pointer",
        display: "grid", placeItems: "center",
        fontSize: 12, fontWeight: 600,
      }}>AC</button>
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <div style={{
          fontSize: 15, lineHeight: "18px", fontWeight: 600,
          color: "var(--text-primary)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>Acme CA</div>
        <div style={{
          fontSize: 11, lineHeight: "14px", color: "var(--text-muted)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>142 clients · Owner</div>
      </div>
      <button aria-label="Notifications" style={{
        position: "relative", width: 40, height: 40, borderRadius: 10,
        border: "none", background: "transparent", cursor: "pointer",
        display: "grid", placeItems: "center",
        color: "var(--text-secondary)",
      }}>
        <BellIcon size={20} />
        <span style={{
          position: "absolute", top: 8, right: 9,
          width: 8, height: 8, borderRadius: 999, background: "var(--danger)",
          border: "2px solid var(--surface)", boxSizing: "content-box",
          marginTop: -2, marginRight: -2,
        }} />
      </button>
      <span style={{
        width: 32, height: 32, borderRadius: 8,
        background: "var(--accent-soft)", color: "var(--accent)",
        display: "grid", placeItems: "center",
        fontSize: 12, fontWeight: 600,
      }}>PM</span>
    </div>
  );
}

function ComplianceHealth() {
  return (
    <div style={{
      marginTop: 16, padding: 16,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{
          fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>Firm compliance health</div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Updated 2 min ago</div>
      </div>
      <div style={{
        marginTop: 12, display: "flex", alignItems: "baseline", gap: 6,
      }}>
        <div style={{
          fontSize: 32, fontWeight: 600, letterSpacing: "-0.02em",
          color: "var(--text-primary)", lineHeight: 1,
        }}>87</div>
        <div style={{ fontSize: 20, fontWeight: 500, color: "var(--text-muted)" }}>/100</div>
        <div style={{
          marginLeft: "auto",
          height: 22, padding: "0 8px", borderRadius: 999,
          background: "var(--success-soft)", color: "var(--success)",
          display: "inline-flex", alignItems: "center",
          fontSize: 11, fontWeight: 500,
        }}>+3 vs last month</div>
      </div>
      <div style={{ marginTop: 16, display: "flex", gap: 2, height: 6 }}>
        <div style={{ width: "60%", background: "var(--success)", borderRadius: "3px 0 0 3px" }} />
        <div style={{ width: "25%", background: "var(--warning)" }} />
        <div style={{ width: "15%", background: "var(--danger)", borderRadius: "0 3px 3px 0" }} />
      </div>
      <div style={{
        marginTop: 12, fontSize: 11, color: "var(--text-muted)", lineHeight: 1.45,
      }}>
        Across 142 clients · 60% compliant · 25% at risk · 15% overdue
      </div>
    </div>
  );
}

function KpiGrid() {
  return (
    <div style={{
      marginTop: 16, display: "grid",
      gridTemplateColumns: "1fr 1fr", gap: 12,
    }}>
      {KPIS.map(k => (
        <div key={k.period} style={{
          minHeight: 96, padding: 12,
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 12,
          display: "flex", flexDirection: "column", gap: 4,
        }}>
          <div style={{
            height: 24, display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <span style={{
              width: 24, height: 24, borderRadius: 6,
              background: k.iconBg, color: k.iconFg,
              display: "grid", placeItems: "center",
            }}>{k.icon}</span>
            <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 500 }}>
              {k.period}
            </span>
          </div>
          <div style={{
            marginTop: 4, fontSize: 28, fontWeight: 600, letterSpacing: "-0.02em",
            color: "var(--text-primary)", lineHeight: 1.1,
          }}>{k.value}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{k.desc}</div>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ title, count, action = "See all" }: {
  title: string; count?: string; action?: string;
}) {
  return (
    <div style={{
      height: 32, display: "flex", alignItems: "center", justifyContent: "space-between",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ fontSize: 17, fontWeight: 600, color: "var(--text-primary)" }}>
          {title}
        </div>
        {count && (
          <span style={{
            height: 18, padding: "0 7px",
            border: "1px solid var(--border)", borderRadius: 6,
            fontSize: 11, color: "var(--text-secondary)",
            display: "inline-flex", alignItems: "center",
          }}>{count}</span>
        )}
      </div>
      <a href="#" style={{
        fontSize: 13, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
      }}>{action}</a>
    </div>
  );
}

function DueSection() {
  return (
    <div style={{ marginTop: 24 }}>
      <SectionHeader title="Due today & tomorrow" />
      <div style={{
        marginTop: 12, display: "flex", flexDirection: "column", gap: 8,
      }}>
        {FILINGS.map((f, i) => (
          <div key={i} style={{
            minHeight: 80, padding: "12px 16px",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderLeft: `3px solid ${f.barTone}`,
            borderRadius: 12,
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <span style={{
              height: 20, padding: "0 6px",
              border: "1px solid var(--border)", borderRadius: 6,
              fontSize: 10, fontWeight: 600, color: "var(--text-secondary)",
              display: "inline-flex", alignItems: "center", flex: "none",
            }}>{f.ret}</span>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{
                fontSize: 15, fontWeight: 500, color: "var(--text-primary)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>{f.title}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{f.sub}</div>
            </div>
            <span style={{
              height: 20, padding: "0 8px", flex: "none",
              background: f.statusBg, color: f.statusFg,
              borderRadius: 999,
              display: "inline-flex", alignItems: "center",
              fontSize: 11, fontWeight: 500,
            }}>{f.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AtRiskSection() {
  return (
    <div style={{ marginTop: 24 }}>
      <SectionHeader title="At-risk clients" count="5" />
      <div style={{
        marginTop: 12, display: "flex", flexDirection: "column", gap: 8,
      }}>
        {AT_RISK.map((c, i) => (
          <div key={i} style={{
            minHeight: 72, padding: "12px 16px",
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 12,
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <div style={{
              width: 40, height: 40, borderRadius: 10, flex: "none",
              background: c.avBg, color: c.avFg,
              display: "grid", placeItems: "center",
              fontSize: 14, fontWeight: 600,
            }}>{c.init}</div>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{
                fontSize: 15, fontWeight: 500, color: "var(--text-primary)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>{c.name}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{c.sub}</div>
            </div>
            <div style={{
              display: "flex", flexDirection: "column",
              alignItems: "flex-end", gap: 6, flex: "none",
            }}>
              <span style={{
                height: 20, padding: "0 8px",
                background: c.statusBg, color: c.statusFg,
                borderRadius: 999,
                display: "inline-flex", alignItems: "center",
                fontSize: 11, fontWeight: 500,
              }}>{c.status}</span>
              <span style={{ color: "var(--text-muted)" }}><ChevronRightIcon size={14} /></span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivitySection() {
  return (
    <div style={{ marginTop: 24 }}>
      <SectionHeader title="Recent activity" />
      <div style={{
        marginTop: 12, padding: 8,
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12,
        display: "flex", flexDirection: "column",
      }}>
        {ACTIVITY.map((a, i) => (
          <div key={i} style={{
            minHeight: 48, padding: 8,
            display: "flex", alignItems: "center", gap: 12,
            borderBottom: i < ACTIVITY.length - 1 ? "1px solid var(--border)" : "none",
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: 999, background: a.dot, flex: "none",
            }} />
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 14, color: "var(--text-primary)" }}>{a.msg}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{a.meta}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TabBar() {
  const tabs = [
    { key: "dashboard", label: "Dashboard", icon: <DashSvg />, active: true },
    { key: "calendar",  label: "Calendar",  icon: <CalendarSvg /> },
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

export default function MobileDashboardPage() {
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
          padding: "8px 16px 96px",
          display: "flex", flexDirection: "column",
        }}>
          <div style={{
            fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
            textTransform: "uppercase", color: "var(--text-muted)", marginTop: 8,
          }}>
            Wednesday, 13 August 2026
          </div>
          <h1 style={{
            margin: "4px 0 0 0",
            fontSize: 28, lineHeight: "36px", fontWeight: 600,
            letterSpacing: "-0.02em", color: "var(--text-primary)",
          }}>
            Compliance overview
          </h1>

          <ComplianceHealth />
          <KpiGrid />
          <DueSection />
          <AtRiskSection />
          <ActivitySection />
        </div>

        {/* FAB */}
        <button aria-label="Create" style={{
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
