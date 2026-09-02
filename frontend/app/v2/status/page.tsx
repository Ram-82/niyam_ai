"use client";

import { useEffect, useState } from "react";
import {
  BellIcon, MoonIcon, ChevronDownIcon, ArrowUpRightIcon, CheckCircleIcon,
  AlertTriangleIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import {
  useStatusData,
  overallState,
  buildServices,
  stateLabel,
  stateColorVar,
  formatRelativeSeconds,
  type ServiceRow,
  type ServiceState,
} from "./useStatusData";

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

function OverallBanner({
  state,
  updatedAt,
  loading,
  onRefresh,
}: {
  state: ServiceState;
  updatedAt: Date | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const [tick, setTick] = useState(0);
  // Re-render every 5s so "updated Xs ago" stays fresh without a full refetch.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);
  void tick;

  const title =
    state === "operational" ? "All systems operational"
    : state === "degraded" ? "Some systems degraded"
    : state === "down" ? "System unreachable"
    : "Live status unknown";
  const tone =
    state === "operational" ? "var(--success)"
    : state === "degraded" ? "var(--warning)"
    : state === "down" ? "var(--danger)"
    : "var(--text-muted)";
  const bg =
    state === "operational" ? "var(--success-soft)"
    : state === "degraded" ? "var(--warning-soft)"
    : state === "down" ? "var(--danger-soft)"
    : "var(--row-hover)";
  const Icon = state === "operational" ? CheckCircleIcon : AlertTriangleIcon;

  return (
    <div style={{
      minHeight: 96, padding: 24,
      background: bg,
      border: `1px solid ${tone}`,
      borderLeft: `3px solid ${tone}`,
      borderRadius: 12,
      boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ color: tone }}><Icon size={22} /></span>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{
            fontSize: 18, fontWeight: 600, color: tone,
          }}>{title}</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {loading ? "Checking…" : `Last checked ${formatRelativeSeconds(updatedAt)}`}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button type="button" onClick={onRefresh} disabled={loading} style={{
          height: 32, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)", color: "var(--text-secondary)",
          fontSize: 12, fontWeight: 500,
          cursor: loading ? "not-allowed" : "pointer",
          opacity: loading ? 0.6 : 1,
          display: "inline-flex", alignItems: "center", gap: 6,
        }}>
          <RefreshSvg size={13} /> {loading ? "Refreshing…" : "Refresh"}
        </button>
        <button type="button" disabled title="Status subscriptions ship later" style={{
          height: 32, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)", color: "var(--text-primary)",
          fontSize: 12, fontWeight: 500, cursor: "not-allowed", opacity: 0.5,
          display: "inline-flex", alignItems: "center", gap: 6,
        }}>
          <BellIcon size={13} /> Subscribe to updates
        </button>
      </div>
    </div>
  );
}

/* --- component card + 90-day strip -------------------------------------- */

function ServiceCard({ row }: { row: ServiceRow }) {
  const { fg, bg } = stateColorVar(row.state);
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
        }}>{row.name}</span>
        <span style={{
          fontSize: 12, color: "var(--text-secondary)",
          maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>{row.detail}</span>
        <span style={{
          height: 20, padding: "0 8px",
          background: bg, color: fg,
          borderRadius: 6,
          display: "inline-flex", alignItems: "center",
          fontSize: 11, fontWeight: 500,
        }}>{stateLabel(row.state)}</span>
      </div>
      <div style={{
        fontSize: 11, color: "var(--text-muted)", fontStyle: "italic",
      }}>
        90-day uptime graph unavailable — historical uptime not persisted.
      </div>
    </div>
  );
}

function Components({ rows }: { rows: ServiceRow[] }) {
  return (
    <div style={{ marginTop: 64 }}>
      <h2 style={{
        margin: 0, fontSize: 24, lineHeight: "32px", fontWeight: 600,
        letterSpacing: "-0.01em", color: "var(--text-primary)",
      }}>Components</h2>
      <div style={{ marginTop: 8, fontSize: 13, color: "var(--text-muted)" }}>
        Live check via <span style={{ fontFamily: "var(--font-mono-v2)" }}>/health</span> +{" "}
        <span style={{ fontFamily: "var(--font-mono-v2)" }}>/readyz</span> · rows without a real
        endpoint are marked "Not monitored via API".
      </div>
      <div style={{
        marginTop: 24, display: "flex", flexDirection: "column", gap: 12,
      }}>
        {rows.map((r) => (
          <ServiceCard key={r.name} row={r} />
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
  const { health, ready, loading, error, lastFetched, reload } = useStatusData();
  const state = overallState(health, ready, error);
  const services = buildServices(health, ready);
  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header />
      <PageHeader />
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 32px 48px" }}>
        <OverallBanner state={state} updatedAt={lastFetched} loading={loading} onRefresh={reload} />
        {error && (
          <div style={{ marginTop: 16 }}>
            <ErrorBanner message={`Health-check probe error: ${error}`} onRetry={reload} />
          </div>
        )}
        <Components rows={services} />
      </div>
      <Footer />
    </div>
  );
}
