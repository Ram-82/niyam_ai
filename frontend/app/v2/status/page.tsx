"use client";

import {
  BellIcon, MoonIcon, ChevronDownIcon, ArrowUpRightIcon, CheckCircleIcon,
} from "@/components/v2/icons";

/* --- inline SVGs --------------------------------------------------------- */

const MonitorSvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <rect x={2} y={4} width={20} height={13} rx={2} />
    <path d="M8 21h8M12 17v4" />
  </svg>
);

const RefreshSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 12a8 8 0 0 1 14-5.3L20 8" />
    <path d="M20 3v5h-5" />
    <path d="M20 12a8 8 0 0 1-14 5.3L4 16" />
    <path d="M4 21v-5h5" />
  </svg>
);

/* --- data ---------------------------------------------------------------- */

const SERVICES = [
  { name: "Web application (frontend)",           uptime: "99.99%" },
  { name: "API (backend)",                        uptime: "99.98%" },
  { name: "GSTN Suvidha Provider integration",    uptime: "99.94%" },
  { name: "AI narrator (Anthropic + Gemini)",     uptime: "99.87%" },
  { name: "WhatsApp Business API",                uptime: "99.99%" },
  { name: "Background workers (RQ)",              uptime: "99.99%" },
];

type IncSev = "MINOR" | "MAJOR";
type Incident = {
  sev: IncSev; title: string; date: string; body: string;
  status: string; duration: string; statusTone: "success" | "warning" | "danger";
};

const INC_AUG: Incident[] = [
  { sev: "MINOR", title: "AI narrator elevated latency", date: "4 Aug 2026",
    body: "Anthropic upstream returned 502s intermittently between 09:14–09:42 IST for ~14% of requests. Failover to Gemini enabled.",
    status: "Resolved", duration: "28m", statusTone: "success" },
  { sev: "MINOR", title: "GSTN portal degraded response", date: "1 Aug 2026",
    body: "GSTN reported degraded response times upstream from 14:30–15:12 IST. 2B pulls automatically retried and succeeded.",
    status: "Resolved", duration: "42m", statusTone: "success" },
];

const INC_JUL: Incident[] = [
  { sev: "MAJOR", title: "AI narrator outage · Anthropic outage", date: "22 Jul 2026",
    body: "Anthropic API returned 5xx globally between 03:00–04:22 UTC. Automatic failover to Gemini kicked in at 03:04 UTC. Customer-visible impact for ~4 min before failover.",
    status: "Resolved", duration: "1h 22m", statusTone: "success" },
];

const INC_JUN: Incident[] = [
  { sev: "MINOR", title: "Scheduled maintenance · database failover", date: "12 Jun 2026",
    body: "Planned 15-min failover window for Postgres 15 → 15.4 upgrade. Zero customer-visible impact.",
    status: "Completed", duration: "12m", statusTone: "success" },
];

const METRICS = [
  { l: "90-day uptime",         v: "99.96%", sub: "SLA target 99.9%",   tone: "var(--success)" },
  { l: "Avg API response",      v: "142ms",  sub: "p50 · GET /health",  tone: "var(--text-muted)" },
  { l: "Incidents this quarter", v: "4",      sub: "3 minor · 1 major", tone: "var(--text-muted)" },
  { l: "Mean time to resolve",  v: "47min",  sub: "vs 60min target",    tone: "var(--text-muted)" },
];

const CHANNELS = ["Email", "SMS", "RSS ↗", "Slack ↗", "Webhook ↗"];

/* --- marketing header --------------------------------------------------- */

function Header() {
  const links = ["Product", "Solutions", "Customers", "Pricing", "Docs ↗", "Company"];
  return (
    <header style={{
      height: 72, position: "sticky", top: 0, zIndex: 10,
      background: "var(--surface)", borderBottom: "1px solid var(--border)",
    }}>
      <div style={{
        maxWidth: 1200, margin: "0 auto", padding: "0 32px", height: "100%",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <a href="#" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
          <span style={{
            width: 24, height: 24, borderRadius: 7, background: "var(--accent)",
            display: "grid", placeItems: "center",
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: 2, background: "#fff",
              transform: "rotate(45deg)",
            }} />
          </span>
          <span style={{
            fontSize: 17, lineHeight: "24px", fontWeight: 600,
            letterSpacing: "-0.01em", color: "var(--text-primary)",
          }}>Niyam AI</span>
        </a>
        <nav style={{ display: "flex", alignItems: "center", gap: 32 }}>
          {links.map(l => (
            <a key={l} href="#" style={{
              fontSize: 14, color: "var(--text-secondary)", textDecoration: "none",
              display: "inline-flex", alignItems: "center", gap: 4,
            }}>{l}</a>
          ))}
        </nav>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button aria-label="Toggle theme" style={{
            width: 40, height: 40, border: "none", background: "transparent",
            borderRadius: 8, cursor: "pointer", color: "var(--text-secondary)",
            display: "grid", placeItems: "center",
          }}>
            <MoonIcon size={18} />
          </button>
          <a href="#" style={{
            fontSize: 14, fontWeight: 500, color: "var(--text-primary)", textDecoration: "none",
          }}>Sign in</a>
          <button style={{
            height: 40, padding: "0 18px", border: "none", borderRadius: 10,
            background: "var(--accent)", color: "#fff",
            fontSize: 14, fontWeight: 500, cursor: "pointer",
          }}>Book a demo</button>
        </div>
      </div>
    </header>
  );
}

/* --- page header block --------------------------------------------------- */

function PageHeader() {
  return (
    <section style={{ padding: "96px 0 32px", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 32px" }}>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Company · Status</div>
        <h1 style={{
          margin: "16px 0 0 0", fontSize: 40, lineHeight: "48px", fontWeight: 600,
          letterSpacing: "-0.02em", color: "var(--text-primary)",
        }}>System status</h1>
      </div>
    </section>
  );
}

/* --- overall banner (success-tinted, all operational) ------------------- */

function OverallBanner() {
  return (
    <div style={{
      minHeight: 96, padding: 24,
      background: "var(--success-soft)",
      border: "1px solid var(--success)",
      borderLeft: "3px solid var(--success)",
      borderRadius: 12,
      boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ color: "var(--success)" }}><CheckCircleIcon size={22} /></span>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{
            fontSize: 18, fontWeight: 600, color: "var(--success)",
          }}>All systems operational</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Last incident: 4 Aug 2026 (9 days ago) · updated 12s ago
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button style={{
          height: 32, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)", color: "var(--text-secondary)",
          fontSize: 12, fontWeight: 500, cursor: "pointer",
          display: "inline-flex", alignItems: "center", gap: 6,
        }}>
          <RefreshSvg size={13} /> Refresh
        </button>
        <button style={{
          height: 32, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)", color: "var(--text-primary)",
          fontSize: 12, fontWeight: 500, cursor: "pointer",
          display: "inline-flex", alignItems: "center", gap: 6,
        }}>
          <BellIcon size={13} /> Subscribe to updates
        </button>
      </div>
    </div>
  );
}

/* --- component card + 90-day strip -------------------------------------- */

function UptimeStrip() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", gap: 2, height: 32, alignItems: "stretch" }}>
        {Array.from({ length: 90 }, (_, i) => (
          <div key={i} style={{
            width: 3, borderRadius: 1, background: "var(--success)",
          }} />
        ))}
      </div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: 11, color: "var(--text-muted)",
        fontVariantNumeric: "tabular-nums",
      }}>
        <span>90 days ago</span>
        <span>Today</span>
      </div>
    </div>
  );
}

function ServiceCard({ name, uptime }: { name: string; uptime: string }) {
  return (
    <div style={{
      padding: 20, background: "var(--surface)",
      border: "1px solid var(--border)", borderRadius: 12,
      boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", flexDirection: "column", gap: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "var(--text-secondary)" }}><MonitorSvg size={16} /></span>
        <span style={{
          flex: 1, fontSize: 15, fontWeight: 500, color: "var(--text-primary)",
        }}>{name}</span>
        <span style={{
          fontSize: 15, fontWeight: 500, color: "var(--text-primary)",
          fontVariantNumeric: "tabular-nums",
        }}>{uptime}</span>
        <span style={{
          height: 20, padding: "0 8px",
          background: "var(--success-soft)", color: "var(--success)",
          borderRadius: 6,
          display: "inline-flex", alignItems: "center",
          fontSize: 11, fontWeight: 500,
        }}>Operational</span>
      </div>
      <UptimeStrip />
    </div>
  );
}

function Components() {
  return (
    <div style={{ marginTop: 64 }}>
      <h2 style={{
        margin: 0, fontSize: 24, lineHeight: "32px", fontWeight: 600,
        letterSpacing: "-0.01em", color: "var(--text-primary)",
      }}>Components</h2>
      <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-muted)" }}>
        Uptime for the last 90 days · updated every 60s
      </div>
      <div style={{
        marginTop: 24, display: "flex", flexDirection: "column", gap: 12,
      }}>
        {SERVICES.map(s => (
          <ServiceCard key={s.name} name={s.name} uptime={s.uptime} />
        ))}
      </div>
    </div>
  );
}

/* --- incident card ------------------------------------------------------- */

function IncidentCard({ inc }: { inc: Incident }) {
  const sevMap = {
    MINOR: { bg: "var(--warning-soft)", fg: "var(--warning)" },
    MAJOR: { bg: "var(--danger-soft)",  fg: "var(--danger)" },
  };
  const sev = sevMap[inc.sev];
  const statusMap = {
    success: { bg: "var(--success-soft)", fg: "var(--success)" },
    warning: { bg: "var(--warning-soft)", fg: "var(--warning)" },
    danger:  { bg: "var(--danger-soft)",  fg: "var(--danger)" },
  };
  const st = statusMap[inc.statusTone];
  return (
    <div style={{
      minHeight: 96, padding: 20,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{
          height: 20, padding: "0 8px",
          background: sev.bg, color: sev.fg,
          borderRadius: 6,
          display: "inline-flex", alignItems: "center",
          fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
        }}>{inc.sev}</span>
        <div style={{
          flex: 1, fontSize: 15, fontWeight: 500, color: "var(--text-primary)",
        }}>{inc.title}</div>
        <div style={{ fontSize: 13, color: "var(--text-muted)", flex: "none" }}>
          {inc.date}
        </div>
      </div>
      <div style={{
        fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)",
      }}>{inc.body}</div>
      <div style={{
        alignSelf: "flex-end", display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{
          height: 20, padding: "0 8px",
          background: st.bg, color: st.fg,
          borderRadius: 6,
          display: "inline-flex", alignItems: "center",
          fontSize: 11, fontWeight: 500,
        }}>{inc.status}</span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{inc.duration}</span>
      </div>
    </div>
  );
}

function IncidentHistory() {
  const monthLabel = (t: string): React.CSSProperties => ({});
  const months = [
    { label: "AUGUST 2026", items: INC_AUG },
    { label: "JULY 2026",   items: INC_JUL },
    { label: "JUNE 2026",   items: INC_JUN },
  ];
  return (
    <div style={{ marginTop: 64 }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <h2 style={{
          margin: 0, fontSize: 24, lineHeight: "32px", fontWeight: 600,
          letterSpacing: "-0.01em", color: "var(--text-primary)",
        }}>Incident history</h2>
        <div style={{
          display: "inline-flex", height: 32,
          border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden",
          background: "var(--surface)",
        }}>
          <button style={{
            padding: "0 14px", fontSize: 12, fontWeight: 500,
            border: "none", cursor: "pointer",
            background: "var(--accent-soft)", color: "var(--accent)",
          }}>Last 90 days</button>
          <button style={{
            padding: "0 14px", fontSize: 12, fontWeight: 500,
            border: "none", cursor: "pointer",
            borderLeft: "1px solid var(--border)",
            background: "transparent", color: "var(--text-secondary)",
          }}>Last 12 months</button>
        </div>
      </div>

      <div style={{
        marginTop: 24, display: "flex", flexDirection: "column", gap: 24,
      }}>
        {months.map(m => (
          <div key={m.label} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{
              fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--text-muted)",
            }}>{m.label}</div>
            {m.items.map(inc => <IncidentCard key={inc.title} inc={inc} />)}
          </div>
        ))}
      </div>
    </div>
  );
}

/* --- metrics ------------------------------------------------------------ */

function Metrics() {
  return (
    <div style={{ marginTop: 64 }}>
      <h2 style={{
        margin: 0, fontSize: 24, lineHeight: "32px", fontWeight: 600,
        letterSpacing: "-0.01em", color: "var(--text-primary)",
      }}>Metrics</h2>
      <div style={{
        marginTop: 24, display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)", gap: 12,
      }}>
        {METRICS.map(m => (
          <div key={m.l} style={{
            minHeight: 96, padding: 20,
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
            display: "flex", flexDirection: "column", gap: 8,
          }}>
            <div style={{
              fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--text-muted)",
            }}>{m.l}</div>
            <div style={{
              fontSize: 24, fontWeight: 600, color: "var(--text-primary)",
            }}>{m.v}</div>
            <div style={{ fontSize: 12, color: m.tone }}>{m.sub}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* --- subscribe row ------------------------------------------------------ */

function Subscribe() {
  return (
    <div style={{
      marginTop: 48, minHeight: 72, padding: "16px 24px",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
      flexWrap: "wrap",
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontSize: 15, fontWeight: 500, color: "var(--text-primary)" }}>
          Subscribe to status updates
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Email, SMS, RSS, Slack, or webhook — pick your channel.
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {CHANNELS.map(c => (
          <button key={c} style={{
            height: 32, padding: "0 14px",
            border: "1px solid var(--border)", borderRadius: 8,
            background: "var(--surface)", color: "var(--text-primary)",
            fontSize: 12, fontWeight: 500, cursor: "pointer",
          }}>{c}</button>
        ))}
      </div>
    </div>
  );
}

/* --- footer ------------------------------------------------------------- */

function Footer() {
  const cols = [
    { title: "PRODUCT",   links: ["Dashboard", "Compliance Calendar", "AI Assistant", "Contract Analysis", "Reports"] },
    { title: "SOLUTIONS", links: ["For CA firms", "For enterprises", "For compliance heads", "Migrate from ClearTax", "Migrate from Tally"] },
    { title: "RESOURCES", links: ["Documentation ↗", "API reference ↗", "Security & DPA", "GST filing calendar", "Blog"] },
    { title: "COMPANY",   links: ["About", "Careers · (2)", "Customers", "Contact", "Legal"] },
  ];
  return (
    <footer style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "96px 0 48px", marginTop: 96,
    }}>
      <div style={{
        maxWidth: 1200, margin: "0 auto", padding: "0 32px",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{
          display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 64,
        }}>
          <div style={{ flex: 1, maxWidth: 336 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                width: 24, height: 24, borderRadius: 7, background: "var(--accent)",
                display: "grid", placeItems: "center",
              }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: "#fff", transform: "rotate(45deg)" }} />
              </span>
              <span style={{
                fontSize: 17, lineHeight: "24px", fontWeight: 600,
                letterSpacing: "-0.01em", color: "var(--text-primary)",
              }}>Niyam AI</span>
            </div>
            <div style={{
              marginTop: 16, fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)",
            }}>
              The compliance workspace for India&apos;s Chartered Accountants.
            </div>
            <a href="#" style={{
              marginTop: 24, display: "inline-flex", alignItems: "center", gap: 8,
              height: 32, padding: "0 12px",
              border: "1px solid var(--border)", borderRadius: 8,
              fontSize: 12, color: "var(--text-secondary)", textDecoration: "none",
            }}>
              <span style={{ width: 8, height: 8, borderRadius: 999, background: "var(--success)" }} />
              System status · All operational
              <ArrowUpRightIcon size={12} />
            </a>
          </div>
          <div style={{ display: "flex", gap: 24 }}>
            {cols.map(col => (
              <div key={col.title} style={{
                width: 160, display: "flex", flexDirection: "column", gap: 12,
              }}>
                <div style={{
                  fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
                  textTransform: "uppercase", color: "var(--text-muted)",
                }}>{col.title}</div>
                {col.links.map(l => (
                  <a key={l} href="#" style={{
                    fontSize: 13, color: "var(--text-secondary)", textDecoration: "none",
                  }}>{l}</a>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div style={{
          marginTop: 48, paddingTop: 24, borderTop: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
        }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            © 2026 Niyam AI Technologies Pvt Ltd · CIN U72900KA2024PTC183456
          </div>
          <div style={{ display: "flex", gap: 24, color: "var(--text-muted)", fontSize: 11 }}>
            {["Terms", "Privacy", "DPA", "Cookies", "Refund policy"].map(l => (
              <a key={l} href="#" style={{ color: "inherit", textDecoration: "none" }}>{l}</a>
            ))}
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              EN <ChevronDownIcon size={10} />
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}

/* --- page --------------------------------------------------------------- */

export default function StatusPage() {
  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header />
      <PageHeader />
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 32px 48px" }}>
        <OverallBanner />
        <Components />
        <IncidentHistory />
        <Metrics />
        <Subscribe />
      </div>
      <Footer />
    </div>
  );
}
