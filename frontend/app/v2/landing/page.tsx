"use client";

import {
  SparklesIcon, ChevronRightIcon, ChevronDownIcon,
  CheckCircleIcon, AlertTriangleIcon, ClockIcon, UsersIcon,
  MessageSquareIcon, ArrowUpRightIcon, PlusIcon, XIcon,
  SunIcon, MoonIcon,
} from "@/components/v2/icons";

/* --- inline SVGs specific to landing ------------------------------------- */

const ShieldSvg = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

const PlaySvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M8 5v14l11-7z" />
  </svg>
);

const ArrowRightSvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);

const QuoteSvg = () => (
  <svg width={20} height={20} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 6H5a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h4v2a3 3 0 0 1-3 3" />
    <path d="M20 6h-4a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h4v2a3 3 0 0 1-3 3" />
  </svg>
);

const LinkSvg = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 1 0-7-7l-1 1" />
    <path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 1 0 7 7l1-1" />
  </svg>
);

const SlidersSvg = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />
  </svg>
);

/* --- style helpers ------------------------------------------------------- */

const container: React.CSSProperties = {
  maxWidth: 1200, margin: "0 auto", padding: "0 32px",
};

const sectionLabel = (icon: React.ReactNode, text: string): React.CSSProperties => ({});
const SectionLabel = ({ icon, text }: { icon: React.ReactNode; text: string }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
    <span style={{ color: "var(--accent)" }}>{icon}</span>
    <span style={{
      fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
      textTransform: "uppercase", color: "var(--accent)",
    }}>{text}</span>
  </div>
);

const HeadingH2 = ({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <h2 style={{
    margin: 0, fontSize: 44, lineHeight: "52px", fontWeight: 600,
    letterSpacing: "-0.02em", color: "var(--text-primary)",
    ...style,
  }}>{children}</h2>
);

const BodyLg = ({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <p style={{
    margin: 0, fontSize: 18, lineHeight: "28px", color: "var(--text-secondary)",
    ...style,
  }}>{children}</p>
);

const BulletList = ({ items }: { items: string[] }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
    {items.map((t, i) => (
      <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <span style={{ color: "var(--success)", flex: "none", marginTop: 3 }}>
          <CheckCircleIcon size={16} />
        </span>
        <div style={{ fontSize: 15, lineHeight: "24px", color: "var(--text-primary)" }}>{t}</div>
      </div>
    ))}
  </div>
);

const CtaPrimary = ({ children }: { children: React.ReactNode }) => (
  <button style={{
    height: 52, padding: "0 24px", border: "none", borderRadius: 12,
    background: "var(--accent)", color: "#fff",
    fontSize: 16, fontWeight: 500, cursor: "pointer",
    display: "inline-flex", alignItems: "center", gap: 8,
  }}>{children}</button>
);

const CtaSecondary = ({ children }: { children: React.ReactNode }) => (
  <button style={{
    height: 52, padding: "0 24px",
    border: "1px solid var(--border-strong)", borderRadius: 12,
    background: "var(--surface)", color: "var(--text-primary)",
    fontSize: 16, fontWeight: 500, cursor: "pointer",
    display: "inline-flex", alignItems: "center", gap: 8,
  }}>{children}</button>
);

/* --- top nav ------------------------------------------------------------- */

function Header() {
  const links = ["Product", "Solutions", "Customers", "Pricing", "Docs ↗", "Company"];
  return (
    <header style={{
      height: 72, position: "sticky", top: 0, zIndex: 10,
      background: "var(--surface)",
      borderBottom: "1px solid var(--border)",
    }}>
      <div style={{
        ...container, height: "100%",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <a href="#" style={{
          display: "flex", alignItems: "center", gap: 8, textDecoration: "none",
        }}>
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
            fontSize: 14, fontWeight: 500, color: "var(--text-primary)",
            textDecoration: "none",
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

/* --- Section 1: Hero ----------------------------------------------------- */

function DashboardMockup() {
  return (
    <div style={{ position: "relative", width: 440, flex: "none" }}>
      <div style={{
        position: "absolute", top: -12, right: 12, zIndex: 2,
        height: 24, padding: "0 10px", borderRadius: 999,
        background: "var(--accent-soft)", color: "var(--accent)",
        display: "inline-flex", alignItems: "center", gap: 6,
        fontSize: 11, fontWeight: 600, letterSpacing: "0.06em",
      }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--accent)" }} />
        LIVE
      </div>
      <div style={{
        height: 560, background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: 12,
        boxShadow: "0 12px 40px rgba(15,23,42,0.10)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        <div style={{
          height: 36, padding: "0 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: "var(--accent)" }} />
            <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-primary)" }}>Niyam AI</span>
          </div>
          <span style={{
            width: 18, height: 18, borderRadius: 999,
            background: "var(--accent-soft)", color: "var(--accent)",
            display: "grid", placeItems: "center", fontSize: 8, fontWeight: 600,
          }}>AV</span>
        </div>
        <div style={{ flex: 1, display: "flex" }}>
          <div style={{
            width: 56, borderRight: "1px solid var(--border)",
            display: "flex", flexDirection: "column", alignItems: "center",
            padding: "10px 0", gap: 8,
          }}>
            {[0, 1, 2, 3, 4, 5].map(i => (
              <div key={i} style={{
                width: 28, height: 24, borderRadius: 6,
                background: i === 0 ? "var(--accent-soft)" : "transparent",
                color: i === 0 ? "var(--accent)" : "var(--text-muted)",
                display: "grid", placeItems: "center",
                fontSize: 10,
              }}>◼</div>
            ))}
          </div>
          <div style={{
            flex: 1, padding: 12, background: "var(--bg)",
            display: "flex", flexDirection: "column", gap: 10,
          }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
              Compliance Overview
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{
                flex: "0 0 60%", padding: 10, border: "1px solid var(--border)", borderRadius: 8,
                background: "var(--surface)",
                display: "flex", flexDirection: "column", gap: 6,
              }}>
                <div style={{
                  fontSize: 8, fontWeight: 500, letterSpacing: "0.06em",
                  textTransform: "uppercase", color: "var(--text-muted)",
                }}>FIRM HEALTH</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 2 }}>
                  <span style={{ fontSize: 26, fontWeight: 600, color: "var(--text-primary)" }}>87</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>/100</span>
                </div>
                <div style={{ display: "flex", gap: 2, height: 5 }}>
                  <div style={{ width: "60%", background: "var(--success)", borderRadius: 2 }} />
                  <div style={{ width: "25%", background: "var(--warning)" }} />
                  <div style={{ width: "15%", background: "var(--danger)", borderRadius: 2 }} />
                </div>
                <div style={{ fontSize: 8, color: "var(--text-muted)" }}>
                  142 clients · updated 2 min ago
                </div>
              </div>
              <div style={{
                flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6,
              }}>
                {[["DEADLINES","23"],["PENDING","8"],["AT RISK","5"],["FILED","47"]].map(([l, v]) => (
                  <div key={l} style={{
                    padding: 7, border: "1px solid var(--border)", borderRadius: 7,
                    background: "var(--surface)",
                    display: "flex", flexDirection: "column", gap: 2,
                  }}>
                    <div style={{
                      fontSize: 7, fontWeight: 500, letterSpacing: "0.06em",
                      textTransform: "uppercase", color: "var(--text-muted)",
                    }}>{l}</div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{
              flex: 1, padding: 10,
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 8, display: "flex", flexDirection: "column", gap: 8,
            }}>
              <div style={{ fontSize: 9, fontWeight: 600, color: "var(--text-primary)" }}>
                AT-RISK CLIENTS
              </div>
              {[
                { init: "RT", name: "Ramesh Textiles Pvt Ltd", status: "Overdue", bg: "var(--danger-soft)", fg: "var(--danger)" },
                { init: "NX", name: "Nova Exports LLP",        status: "Due 2d",  bg: "var(--warning-soft)", fg: "var(--warning)" },
                { init: "ST", name: "Sundar Traders",           status: "Blocker", bg: "var(--danger-soft)", fg: "var(--danger)" },
              ].map((r, i, arr) => (
                <div key={r.init} style={{
                  display: "flex", alignItems: "center", gap: 6,
                  paddingBottom: 7, borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none",
                }}>
                  <span style={{
                    width: 18, height: 18, borderRadius: 5,
                    background: "var(--accent-soft)", color: "var(--accent)",
                    display: "grid", placeItems: "center",
                    fontSize: 7, fontWeight: 600,
                  }}>{r.init}</span>
                  <span style={{
                    flex: 1, fontSize: 9, color: "var(--text-primary)",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>{r.name}</span>
                  <span style={{
                    padding: "1px 6px", borderRadius: 999,
                    background: r.bg, color: r.fg,
                    fontSize: 8, fontWeight: 500,
                  }}>{r.status}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section style={{ background: "var(--bg)", padding: "160px 0 128px" }}>
      <div style={{ ...container, display: "flex", gap: 64, alignItems: "flex-start" }}>
        <div style={{ flex: 1, maxWidth: 640, display: "flex", flexDirection: "column" }}>
          <a href="#" style={{
            alignSelf: "flex-start", height: 36, padding: "0 16px",
            border: "1px solid var(--border)", borderRadius: 999,
            display: "inline-flex", alignItems: "center", gap: 8,
            fontSize: 13, color: "var(--text-secondary)", textDecoration: "none",
          }}>
            <span style={{ color: "var(--accent)" }}><SparklesIcon size={14} /></span>
            New · AI narrator now supports Hindi, Kannada &amp; Marathi
            <span style={{ color: "var(--text-muted)" }}><ChevronRightIcon size={14} /></span>
          </a>
          <h1 style={{
            margin: "32px 0 0 0",
            fontSize: 64, lineHeight: "72px", fontWeight: 600,
            letterSpacing: "-0.03em", color: "var(--text-primary)",
          }}>
            The compliance workspace for India&apos;s Chartered Accountants.
          </h1>
          <p style={{
            margin: "24px 0 0 0", maxWidth: 600,
            fontSize: 18, lineHeight: "28px", color: "var(--text-secondary)",
          }}>
            Niyam AI pulls your clients&apos; GST data, flags every risk before you file,
            and drafts board-ready reports in plain English. Built with the practices
            that file 1 in every 800 GST returns in India.
          </p>
          <div style={{ marginTop: 40, display: "flex", gap: 12 }}>
            <CtaPrimary>Book a 20-minute demo <ArrowRightSvg /></CtaPrimary>
            <CtaSecondary><PlaySvg /> Watch the 4-minute tour</CtaSecondary>
          </div>
          <div style={{ marginTop: 16, fontSize: 12, color: "var(--text-muted)" }}>
            No credit card. Sandbox access with real GSTN mock data on day 1.
          </div>
          <div style={{ marginTop: 48, display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{
              fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--text-muted)",
            }}>Trusted by 2,400+ CA firms</div>
            <div style={{ display: "flex" }}>
              {["GC","MA","KA","CS"].map((s, i) => (
                <span key={s} style={{
                  width: 32, height: 32, borderRadius: 999,
                  marginLeft: i === 0 ? 0 : -8,
                  border: "2px solid var(--bg)",
                  background: "var(--accent-soft)", color: "var(--accent)",
                  display: "grid", placeItems: "center",
                  fontSize: 11, fontWeight: 600,
                }}>{s}</span>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>and 6,842 CAs</div>
          </div>
        </div>
        <DashboardMockup />
      </div>
    </section>
  );
}

/* --- Section 2: Trust Strip --------------------------------------------- */

function TrustStrip() {
  const logos = ["GANESAN & CO", "MALHOTRA ADVISORY", "KAPOOR ASSOCIATES",
                 "CHANDRA & SONS", "BHARAT AUDIT LLP", "NOVA COMPLIANCE"];
  return (
    <section style={{
      background: "var(--surface)",
      borderTop: "1px solid var(--border)",
      borderBottom: "1px solid var(--border)",
      padding: "64px 0",
    }}>
      <div style={{ ...container, display: "flex", flexDirection: "column", gap: 24 }}>
        <div style={{
          fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-muted)",
          textAlign: "center",
        }}>
          Trusted by leading CA firms across India
        </div>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
        }}>
          {logos.map(l => (
            <span key={l} style={{
              fontSize: 15, fontWeight: 600, letterSpacing: "0.02em",
              color: "var(--text-muted)", opacity: 0.7,
            }}>{l}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --- Section 3: Problem -------------------------------------------------- */

function Problem() {
  const cards = [
    { icon: <ClockIcon size={18} />, tint: "danger",
      title: "9 days per client, per month",
      body: "Manual reconciliation alone consumes 2/3 of your team's July, October, and January." },
    { icon: <AlertTriangleIcon size={18} />, tint: "warning",
      title: "Errors surface after filing",
      body: "Missing HSN codes, wrong place-of-supply, unclaimed ITC — you find them when the client's tax officer does." },
    { icon: <UsersIcon size={18} />, tint: "accent",
      title: "New associates take 6 months to be safe",
      body: "Every rule change means re-training. Reviews pile up on your partners' desks and cycle time stretches." },
  ];
  const tintMap: Record<string, [string, string]> = {
    danger:  ["var(--danger-soft)",  "var(--danger)"],
    warning: ["var(--warning-soft)", "var(--warning)"],
    accent:  ["var(--accent-soft)",  "var(--accent)"],
  };
  return (
    <section style={{ background: "var(--bg)", padding: "128px 0" }}>
      <div style={{ ...container, display: "flex", flexDirection: "column" }}>
        <SectionLabel icon={<AlertTriangleIcon size={14} />} text="The problem" />
        <HeadingH2 style={{ marginTop: 16, maxWidth: 720 }}>
          GST prep is still a spreadsheet marathon.
        </HeadingH2>
        <BodyLg style={{ marginTop: 24, maxWidth: 720 }}>
          Your team spends the third week of every month reconciling 2B against purchase
          registers, chasing suppliers on WhatsApp, and formatting summaries for clients.
          Every filing carries risk you can&apos;t fully see until it&apos;s too late.
        </BodyLg>
        <div style={{
          marginTop: 64, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 32,
        }}>
          {cards.map((c, i) => {
            const [bg, fg] = tintMap[c.tint];
            return (
              <div key={i} style={{
                display: "flex", flexDirection: "column", gap: 16,
              }}>
                <span style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: bg, color: fg,
                  display: "grid", placeItems: "center",
                }}>{c.icon}</span>
                <div style={{
                  fontSize: 24, lineHeight: "32px", fontWeight: 600,
                  letterSpacing: "-0.01em", color: "var(--text-primary)",
                }}>{c.title}</div>
                <div style={{ fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)" }}>
                  {c.body}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* --- Section 4: Product Tour -------------------------------------------- */

function ReconciliationCard() {
  const rows = [
    { inv: "INV-2607-0142", sup: "Sri Venkat Yarns",     amt: "₹4,26,780", st: "Matched",  stBg: "var(--success-soft)", stFg: "var(--success)" },
    { inv: "INV-2607-0138", sup: "Deccan Dyes & Chem",   amt: "₹1,18,450", st: "Matched",  stBg: "var(--success-soft)", stFg: "var(--success)" },
    { inv: "INV-2607-0121", sup: "Kaveri Packaging",     amt: "₹62,300",   st: "Probable", stBg: "var(--warning-soft)", stFg: "var(--warning)" },
    { inv: "INV-2607-0119", sup: "Anand Transport Co",   amt: "₹38,900",   st: "Default",  stBg: "var(--danger-soft)",  stFg: "var(--danger)" },
    { inv: "INV-2607-0104", sup: "Hosur Machine Tools",  amt: "₹92,150",   st: "Default",  stBg: "var(--danger-soft)",  stFg: "var(--danger)" },
    { inv: "INV-2607-0098", sup: "Mysore Cotton Mills",  amt: "₹24,906",   st: "Missing",  stBg: "transparent",         stFg: "var(--text-secondary)" },
  ];
  const kpis = [
    { l: "MATCHED",  v: "10", tone: "var(--success)" },
    { l: "PROBABLE", v: "2",  tone: "var(--warning)" },
    { l: "DEFAULT",  v: "6",  tone: "var(--danger)" },
    { l: "MISSING",  v: "3",  tone: "var(--text-primary)" },
    { l: "CDN",      v: "0",  tone: "var(--text-primary)" },
  ];
  return (
    <div style={{
      flex: 1, padding: 24,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
    }}>
      <div style={{ display: "flex", gap: 8 }}>
        {kpis.map(k => (
          <div key={k.l} style={{
            flex: 1, padding: 8, border: "1px solid var(--border)", borderRadius: 8,
            display: "flex", flexDirection: "column", gap: 2,
          }}>
            <div style={{
              fontSize: 9, fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--text-muted)",
            }}>{k.l}</div>
            <div style={{ fontSize: 20, fontWeight: 600, color: k.tone }}>{k.v}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 16 }}>
        <div style={{
          height: 32, display: "flex", gap: 12, alignItems: "center",
          borderBottom: "1px solid var(--border)",
          fontSize: 9, fontWeight: 500, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>
          <div style={{ width: 130 }}>Invoice</div>
          <div style={{ flex: 1 }}>Supplier</div>
          <div style={{ width: 80, textAlign: "right" }}>Taxable</div>
          <div style={{ width: 76, textAlign: "right" }}>Status</div>
        </div>
        {rows.map((r, i) => (
          <div key={i} style={{
            height: 40, display: "flex", gap: 12, alignItems: "center",
            borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none",
            fontSize: 12,
          }}>
            <div style={{ width: 130, fontFamily: "var(--font-mono-v2)", color: "var(--text-primary)" }}>{r.inv}</div>
            <div style={{ flex: 1, color: "var(--text-primary)" }}>{r.sup}</div>
            <div style={{ width: 80, textAlign: "right", fontFamily: "var(--font-mono-v2)", color: "var(--text-secondary)" }}>{r.amt}</div>
            <div style={{ width: 76, textAlign: "right" }}>
              <span style={{
                padding: "2px 8px", borderRadius: 999,
                background: r.stBg, color: r.stFg,
                border: r.st === "Missing" ? "1px solid var(--border)" : "none",
                fontSize: 10, fontWeight: 500,
              }}>{r.st}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FilingWorkflowCard() {
  const steps = [
    { label: "Data ingest",    state: "done" },
    { label: "Validation",     state: "done" },
    { label: "Reconciliation", state: "done" },
    { label: "Computation",    state: "done" },
    { label: "CA review",      state: "active" },
    { label: "File to GSTN",   state: "pending" },
  ];
  return (
    <div style={{
      flex: 1, padding: 24,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", flexDirection: "column", gap: 16,
    }}>
      <div style={{
        fontSize: 9, fontWeight: 500, letterSpacing: "0.06em",
        textTransform: "uppercase", color: "var(--text-muted)",
      }}>FILING WORKFLOW</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {steps.map(s => {
          const bg = s.state === "done" ? "var(--success-soft)"
                   : s.state === "active" ? "var(--accent)"
                   : "var(--surface)";
          const fg = s.state === "done" ? "var(--success)"
                   : s.state === "active" ? "#fff"
                   : "var(--text-muted)";
          const border = s.state === "pending" ? "2px solid var(--border-strong)" : "none";
          return (
            <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                width: 18, height: 18, borderRadius: 999,
                background: bg, color: fg, border,
                display: "grid", placeItems: "center",
                fontSize: 10,
              }}>
                {s.state === "done" ? "✓" : s.state === "active" ? "●" : ""}
              </span>
              <span style={{
                fontSize: 11,
                fontWeight: s.state === "active" ? 500 : 400,
                color: s.state === "pending" ? "var(--text-muted)" : "var(--text-primary)",
              }}>{s.label}</span>
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
        {[
          { l: "OUTWARD TAX",  v: "₹42,68,780", bar: "var(--accent)" },
          { l: "ITC AVAILABLE", v: "₹8,42,180",  bar: "var(--success)" },
          { l: "NET IN CASH",   v: "₹34,26,600", bar: "var(--warning)" },
        ].map(m => (
          <div key={m.l} style={{
            flex: 1, padding: 10,
            border: "1px solid var(--border)",
            borderLeft: `3px solid ${m.bar}`,
            borderRadius: 8,
            display: "flex", flexDirection: "column", gap: 3,
          }}>
            <div style={{
              fontSize: 8, fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--text-muted)",
            }}>{m.l}</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{m.v}</div>
          </div>
        ))}
      </div>
      <div style={{
        padding: 12, borderRadius: 8,
        background: "#FEF5F5",
        border: "1px solid var(--danger)",
        borderLeft: "3px solid var(--danger)",
        display: "flex", flexDirection: "column", gap: 6,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--danger)" }}>
          <XIcon size={13} />
          <div style={{ fontSize: 12, fontWeight: 600 }}>2 blockers before you can file</div>
        </div>
        <div style={{
          paddingBottom: 6, borderBottom: "1px solid #F3C7C7",
          fontSize: 11, lineHeight: "16px", color: "var(--text-secondary)",
        }}>
          Invoice INV-2607-0142 has invalid HSN 998321 for supply of textiles
        </div>
        <div style={{ fontSize: 11, lineHeight: "16px", color: "var(--text-secondary)" }}>
          3 2B entries missing from purchase register (₹1,24,906.26)
        </div>
      </div>
      <button style={{
        alignSelf: "flex-end", height: 28, padding: "0 12px",
        border: "none", borderRadius: 8,
        background: "var(--accent)", color: "#fff",
        fontSize: 11, fontWeight: 500, opacity: 0.6, cursor: "not-allowed",
      }}>File to GSTN</button>
    </div>
  );
}

function AiResearchCard() {
  return (
    <div style={{
      flex: 1, padding: 24,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
      display: "flex", flexDirection: "column", gap: 14,
    }}>
      <div style={{
        alignSelf: "flex-end", maxWidth: 300, padding: "10px 12px",
        borderRadius: 10, background: "var(--accent-soft)",
        fontSize: 12, lineHeight: "18px", color: "var(--text-primary)",
      }}>
        Is ITC available on food coupons given to employees as part of CTC?
        Karnataka IT services company, FY 2025-26.
      </div>
      <div style={{
        padding: "10px 12px",
        background: "#FEF5F5", borderLeft: "3px solid var(--danger)",
        borderRadius: 8,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{ color: "var(--danger)", flex: "none" }}><XIcon size={14} /></span>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--danger)" }}>Not eligible</div>
        <div style={{ color: "var(--text-muted)" }}>·</div>
        <div style={{
          fontSize: 12, color: "var(--text-primary)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>Blocked u/s 17(5)(b)(i) of CGST Act</div>
      </div>
      <div style={{ fontSize: 12, lineHeight: "20px", color: "var(--text-secondary)" }}>
        ITC on food and beverages supplied to employees is blocked under Section 17(5)(b)(i)
        of the CGST Act, 2017{" "}
        <span style={{
          padding: "0 5px", borderRadius: 999,
          background: "var(--accent-soft)", color: "var(--accent)",
          fontSize: 10, fontWeight: 600,
        }}>[1]</span>. The proviso — obligatory under a law in force — does not apply to a
        private IT services company{" "}
        <span style={{
          padding: "0 5px", borderRadius: 999,
          background: "var(--accent-soft)", color: "var(--accent)",
          fontSize: 10, fontWeight: 600,
        }}>[2]</span>.
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {[
          { badge: "CGST ACT",  bg: "var(--accent-soft)",  fg: "var(--accent)",
            title: "Section 17(5)(b)", sub: "Blocked credits" },
          { badge: "CIRCULAR", bg: "var(--warning-soft)", fg: "var(--warning)",
            title: "172/04/2022-GST",  sub: "Perquisites clarification" },
          { badge: "AAR",       bg: "transparent",         fg: "var(--text-secondary)",
            title: "KAR/AAR/12/2023",  sub: "Karnataka authority" },
        ].map(s => (
          <div key={s.badge} style={{
            flex: 1, padding: 10, border: "1px solid var(--border)",
            borderRadius: 8, display: "flex", flexDirection: "column", gap: 6,
          }}>
            <span style={{
              alignSelf: "flex-start", padding: "1px 6px", borderRadius: 5,
              background: s.bg, color: s.fg,
              border: s.badge === "AAR" ? "1px solid var(--border)" : "none",
              fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}>{s.badge}</span>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{s.title}</div>
            <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{s.sub}</div>
          </div>
        ))}
      </div>
      <div style={{ alignSelf: "flex-end", fontSize: 10, color: "var(--text-muted)" }}>
        Answered in 3.2s · 4 sources
      </div>
    </div>
  );
}

function ProductTour() {
  return (
    <section style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "128px 0",
    }}>
      <div style={{ ...container, display: "flex", flexDirection: "column" }}>
        <SectionLabel icon={<ArrowRightSvg size={14} />} text="How Niyam changes that" />
        <HeadingH2 style={{ marginTop: 16, maxWidth: 900 }}>
          Four modules. One workspace. Zero spreadsheets.
        </HeadingH2>
        <BodyLg style={{ marginTop: 16, maxWidth: 720 }}>
          Built for how CA firms actually work — client-first, review-gated,
          audit-trailed by default.
        </BodyLg>

        <div style={{ marginTop: 80, display: "flex", flexDirection: "column", gap: 96 }}>
          {/* Module 1: Reconciliation */}
          <div style={{ display: "flex", gap: 64, alignItems: "center" }}>
            <div style={{ flex: 1, maxWidth: 480, display: "flex", flexDirection: "column", gap: 16 }}>
              <SectionLabel icon={<CheckCircleIcon size={14} />} text="Reconciliation" />
              <div style={{
                fontSize: 32, lineHeight: "40px", fontWeight: 600,
                letterSpacing: "-0.02em", color: "var(--text-primary)",
              }}>Match every 2B invoice in seconds, not hours.</div>
              <BodyLg style={{ fontSize: 15, lineHeight: "24px" }}>
                Niyam pulls GSTR-2B directly from GSTN, matches against your purchase
                register using rules your firm has already agreed on, and shows you
                exactly where the gaps are.
              </BodyLg>
              <div style={{ marginTop: 8 }}>
                <BulletList items={[
                  "21 invoices auto-classified into 5 buckets (matched / probable / supplier default / missing / CDN)",
                  "Fuzzy match with human-in-the-loop confirm for edge cases",
                  "One-tap chase suppliers via WhatsApp when a default is confirmed",
                ]} />
              </div>
              <a href="#" style={{ fontSize: 14, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
                Explore reconciliation ↗
              </a>
            </div>
            <ReconciliationCard />
          </div>

          {/* Module 2: Pre-filing intelligence */}
          <div style={{ display: "flex", gap: 64, alignItems: "center", flexDirection: "row-reverse" }}>
            <div style={{ flex: 1, maxWidth: 480, display: "flex", flexDirection: "column", gap: 16 }}>
              <SectionLabel icon={<ShieldSvg size={14} />} text="Pre-filing intelligence" />
              <div style={{
                fontSize: 32, lineHeight: "40px", fontWeight: 600,
                letterSpacing: "-0.02em", color: "var(--text-primary)",
              }}>Every rule, every return, checked before the client sees it.</div>
              <BodyLg style={{ fontSize: 15, lineHeight: "24px" }}>
                Niyam&apos;s rule pack runs 40+ validators against your client&apos;s data —
                HSN, place of supply, state code, threshold triggers, RCM applicability —
                and flags each blocker with the exact statute and how to fix it.
              </BodyLg>
              <div style={{ marginTop: 8 }}>
                <BulletList items={[
                  "Firm-editable rule pack — your policy, your defaults",
                  "Blocker-gated file button that cannot be clicked with open errors",
                  "Every filing carries a version-stamped audit trail",
                ]} />
              </div>
              <a href="#" style={{ fontSize: 14, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
                See the validator ↗
              </a>
            </div>
            <FilingWorkflowCard />
          </div>

          {/* Module 3: AI Research Assistant */}
          <div style={{ display: "flex", gap: 64, alignItems: "center" }}>
            <div style={{ flex: 1, maxWidth: 480, display: "flex", flexDirection: "column", gap: 16 }}>
              <SectionLabel icon={<SparklesIcon size={14} />} text="AI research assistant" />
              <div style={{
                fontSize: 32, lineHeight: "40px", fontWeight: 600,
                letterSpacing: "-0.02em", color: "var(--text-primary)",
              }}>Cite CGST, Income Tax, Companies Act — with sources, in seconds.</div>
              <BodyLg style={{ fontSize: 15, lineHeight: "24px" }}>
                Ask any tax or compliance question in plain English. Niyam answers with a
                verdict, the reasoning, and every source document cited — Section,
                Circular, Case Law — that a Partner would expect to see.
              </BodyLg>
              <div style={{ marginTop: 8 }}>
                <BulletList items={[
                  "Verdict-first answers with inline [1][2] citations",
                  "Every response validated against your firm's rule pack",
                  "Choose your model — Anthropic Claude or Google Gemini",
                ]} />
              </div>
              <a href="#" style={{ fontSize: 14, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
                Read the security note ↗
              </a>
            </div>
            <AiResearchCard />
          </div>
        </div>
      </div>
    </section>
  );
}

/* --- Section 5: Stats ---------------------------------------------------- */

function Stats() {
  const stats = [
    { n: "2,400+",     l: "CA firms trust Niyam",      s: "Across 26 states" },
    { n: "1.2 M",      l: "Filings per year",           s: "97.4% on-time rate" },
    { n: "₹9,400 Cr",  l: "Compliance value processed", s: "In FY 2025-26" },
    { n: "412 hrs",    l: "Time saved per firm/year",   s: "vs manual baseline" },
  ];
  return (
    <section style={{ background: "var(--bg)", padding: "96px 0" }}>
      <div style={{ ...container, display: "grid", gridTemplateColumns: "repeat(4, 1fr)" }}>
        {stats.map((s, i) => (
          <div key={i} style={{
            padding: "24px 32px",
            borderLeft: i > 0 ? "1px solid var(--border)" : "none",
            display: "flex", flexDirection: "column", gap: 8,
          }}>
            <div style={{
              fontSize: 44, lineHeight: "52px", fontWeight: 600,
              letterSpacing: "-0.02em", color: "var(--text-primary)",
            }}>{s.n}</div>
            <div style={{
              fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--text-muted)",
            }}>{s.l}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{s.s}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* --- Section 6: Testimonials --------------------------------------------- */

function Testimonials() {
  const cards = [
    { quote: "Niyam cut our July filing cycle from nine days to three. It's the first tool my whole team asks for on day one.",
      init: "MG", name: "Meera Ganesan", role: "Managing Partner, Ganesan & Co · Chennai" },
    { quote: "The AI research is the part I didn't expect to love. Every answer cites the actual Section or Circular — I trust it because I can verify it.",
      init: "RM", name: "Rohit Malhotra", role: "Founding Partner, Malhotra Advisory LLP · Mumbai" },
    { quote: "Onboarded 218 clients from Tally in one afternoon. Our first month's filings had zero manual reconciliation errors. Zero.",
      init: "KS", name: "Kavya Suresh", role: "Compliance Head, Bharat Steel Industries · Kolkata" },
  ];
  return (
    <section style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "128px 0",
    }}>
      <div style={{ ...container, display: "flex", flexDirection: "column" }}>
        <SectionLabel icon={<MessageSquareIcon size={14} />} text="Customers" />
        <HeadingH2 style={{ marginTop: 16 }}>
          Practices of every size ship faster on Niyam.
        </HeadingH2>
        <div style={{
          marginTop: 64, display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)", gap: 24,
        }}>
          {cards.map((c, i) => (
            <div key={i} style={{
              padding: 32, background: "var(--surface)",
              border: "1px solid var(--border)", borderRadius: 12,
              boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
              display: "flex", flexDirection: "column", minHeight: 320,
            }}>
              <span style={{ color: "var(--text-muted)" }}><QuoteSvg /></span>
              <div style={{
                marginTop: 16, flex: 1,
                fontSize: 18, lineHeight: "28px", color: "var(--text-primary)",
              }}>{c.quote}</div>
              <div style={{
                marginTop: 24, paddingTop: 24, borderTop: "1px solid var(--border)",
                display: "flex", alignItems: "center", gap: 12,
              }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: "var(--accent-soft)", color: "var(--accent)",
                  display: "grid", placeItems: "center",
                  fontSize: 14, fontWeight: 600,
                }}>{c.init}</div>
                <div>
                  <div style={{ fontSize: 14, lineHeight: "20px", fontWeight: 500, color: "var(--text-primary)" }}>
                    {c.name}
                  </div>
                  <div style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
                    {c.role}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
        <a href="#" style={{
          marginTop: 48, alignSelf: "center",
          fontSize: 16, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
        }}>Read all 60 case studies ↗</a>
      </div>
    </section>
  );
}

/* --- Section 7: Integrations --------------------------------------------- */

function Integrations() {
  const cats = [
    { title: "GSPS",          tools: ["WhiteBooks", "Cygnet", "Alankit", "ClearTax"],
      desc: "Certified GSTN Suvidha Providers", more: "3 more ↗" },
    { title: "ACCOUNTING",    tools: ["Tally", "Zoho Books", "QuickBooks", "Busy"],
      desc: "One-click purchase register import", more: "5 more ↗" },
    { title: "E-INVOICING",   tools: ["IRIS", "ClearIRP", "IRISGST", "Cygnet IRP"],
      desc: "IRN generation for turnover > ₹5Cr", more: "2 more ↗" },
    { title: "COMMUNICATION", tools: ["WhatsApp Biz", "Gmail", "Outlook", "Slack"],
      desc: "Client chase templates + broadcasts", more: "4 more ↗" },
    { title: "IDENTITY",      tools: ["Google WS", "Microsoft 365", "Okta", "JumpCloud"],
      desc: "SSO on Growth and Enterprise plans", more: "SAML ↗" },
  ];
  return (
    <section style={{ background: "var(--bg)", padding: "128px 0" }}>
      <div style={{ ...container, display: "flex", flexDirection: "column" }}>
        <SectionLabel icon={<LinkSvg size={14} />} text="Integrations" />
        <HeadingH2 style={{ marginTop: 16 }}>
          Fits into the tools your firm already uses.
        </HeadingH2>
        <BodyLg style={{ marginTop: 16, maxWidth: 720 }}>
          Niyam connects to your GSP, your accounting stack, and your communication
          channels — no re-training required.
        </BodyLg>
        <div style={{
          marginTop: 64, display: "grid",
          gridTemplateColumns: "repeat(5, 1fr)", gap: 24,
        }}>
          {cats.map(c => (
            <div key={c.title} style={{
              padding: 20, background: "var(--surface)",
              border: "1px solid var(--border)", borderRadius: 12,
              boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
              display: "flex", flexDirection: "column", minHeight: 220,
            }}>
              <div style={{
                fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
                textTransform: "uppercase", color: "var(--text-muted)",
              }}>{c.title}</div>
              <div style={{
                marginTop: 12, display: "grid",
                gridTemplateColumns: "1fr 1fr", gap: 6,
              }}>
                {c.tools.map(t => (
                  <div key={t} style={{
                    height: 28, border: "1px solid var(--border)", borderRadius: 6,
                    display: "grid", placeItems: "center",
                    fontSize: 10, fontWeight: 600, color: "var(--text-secondary)",
                    opacity: 0.8, padding: "0 6px", textAlign: "center",
                  }}>{t}</div>
                ))}
              </div>
              <div style={{
                marginTop: 16, fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)",
              }}>{c.desc}</div>
              <a href="#" style={{
                marginTop: "auto", paddingTop: 16,
                fontSize: 11, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
              }}>{c.more}</a>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --- Section 8: Security ------------------------------------------------- */

function Security() {
  const badges = [
    { l: "SOC 2 · TYPE II", s: "AICPA" },
    { l: "ISO 27001 · 2022", s: "Info sec mgmt" },
    { l: "GSTN GSP", s: "Certified partner" },
    { l: "DPDP · READY", s: "India privacy act" },
  ];
  return (
    <section style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "128px 0",
    }}>
      <div style={{ ...container, display: "flex", gap: 64, alignItems: "flex-start" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <SectionLabel icon={<ShieldSvg size={14} />} text="Security & compliance" />
          <HeadingH2 style={{ marginTop: 16, maxWidth: 520 }}>
            Your clients&apos; data is treated exactly the way a CA would want.
          </HeadingH2>
          <BodyLg style={{ marginTop: 24, maxWidth: 480, fontSize: 15, lineHeight: "24px" }}>
            Every rupee, every invoice, every 2B row is stored in India, encrypted at rest,
            and access-controlled via RLS at the database layer. LLM-optional — every AI
            feature is opt-in per firm.
          </BodyLg>
          <div style={{ marginTop: 24 }}>
            <BulletList items={[
              "SOC 2 Type II · ISO 27001 certified",
              "India-region storage on tier-3 hosted infrastructure",
              "DPDP Act 2023 compliant · MSA with data processing addendum",
              "GSTN GSP-certified partner integrations",
            ]} />
          </div>
          <a href="#" style={{
            marginTop: 24, fontSize: 15, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
          }}>Read our security page ↗</a>
        </div>
        <div style={{
          width: 400, flex: "none",
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24,
          justifyItems: "center",
        }}>
          {badges.map(b => (
            <div key={b.l} style={{
              width: 160, height: 120, padding: 16,
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 12, boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 6,
              textAlign: "center",
            }}>
              <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: "0.02em", color: "var(--text-primary)" }}>
                {b.l}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{b.s}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --- Section 9: Pricing -------------------------------------------------- */

function Pricing() {
  const tiers = [
    { title: "Basic", sub: "Solo practice / small firm",
      price: "₹399", unit: "/client/mo",
      desc: "For firms of 1–3 CAs starting the digital shift.",
      features: [
        "Up to 40 active clients",
        "GST reconciliation + validation + filing",
        "Template narrator (no LLM)",
        "Email support",
      ],
      cta: "Start free trial", primary: false, popular: false },
    { title: "Growth", sub: "Mid-size CA firm",
      price: "₹699", unit: "/client/mo",
      desc: "For firms handling 40–500 clients across multiple states.",
      features: [
        "Unlimited clients",
        "AI Assistant + LLM narrator (Anthropic or Gemini)",
        "WhatsApp Business + email templates",
        "Custom rule pack per firm",
        "SSO (Google, Microsoft)",
        "Priority chat + phone support",
      ],
      cta: "Start Growth trial", primary: true, popular: true },
    { title: "Enterprise", sub: "Large firms + corporate compliance",
      price: "Contact sales", unit: "",
      desc: "For 500+ clients, SLA, and custom deployment.",
      features: [
        "Everything in Growth",
        "SAML SSO + SCIM provisioning",
        "Dedicated GSP + WhatsApp Business account",
        "On-prem or VPC deployment",
        "Custom SLAs + 24/7 support",
        "Dedicated CSM + solutions architect",
      ],
      cta: "Contact sales", primary: false, popular: false },
  ];
  return (
    <section style={{ background: "var(--bg)", padding: "128px 0" }}>
      <div style={{ ...container, display: "flex", flexDirection: "column" }}>
        <SectionLabel icon={<SlidersSvg size={14} />} text="Pricing" />
        <HeadingH2 style={{ marginTop: 16 }}>
          Priced per active client, not per user.
        </HeadingH2>
        <BodyLg style={{ marginTop: 16, maxWidth: 720 }}>
          Bring your whole team. All plans include unlimited seats.
        </BodyLg>
        <div style={{
          marginTop: 68, display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)", gap: 24,
          alignItems: "stretch",
        }}>
          {tiers.map(t => (
            <div key={t.title} style={{
              position: "relative",
              padding: 32,
              background: "var(--surface)",
              border: t.popular ? "2px solid var(--accent)" : "1px solid var(--border)",
              borderRadius: 12,
              boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
              display: "flex", flexDirection: "column", minHeight: 480,
            }}>
              {t.popular && (
                <div style={{
                  position: "absolute", top: -14, left: "50%", transform: "translateX(-50%)",
                  height: 24, padding: "0 12px", borderRadius: 999,
                  background: "var(--accent)", color: "#fff",
                  display: "inline-flex", alignItems: "center",
                  fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
                }}>MOST POPULAR</div>
              )}
              <div style={{
                fontSize: 24, lineHeight: "32px", fontWeight: 600,
                letterSpacing: "-0.01em", color: "var(--text-primary)",
              }}>{t.title}</div>
              <div style={{
                marginTop: 4,
                fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
                textTransform: "uppercase", color: "var(--text-muted)",
              }}>{t.sub}</div>
              <div style={{ marginTop: 24, display: "flex", alignItems: "baseline", gap: 2 }}>
                {t.price === "Contact sales" ? (
                  <div style={{
                    fontSize: 32, lineHeight: "52px", fontWeight: 600,
                    letterSpacing: "-0.02em", color: "var(--text-primary)",
                  }}>{t.price}</div>
                ) : (
                  <>
                    <div style={{ fontSize: 24, fontWeight: 600, color: "var(--text-primary)" }}>
                      {t.price.charAt(0)}
                    </div>
                    <div style={{
                      fontSize: 44, lineHeight: "52px", fontWeight: 600,
                      letterSpacing: "-0.02em", color: "var(--text-primary)",
                    }}>{t.price.slice(1)}</div>
                    <div style={{ fontSize: 14, color: "var(--text-muted)", marginLeft: 6 }}>{t.unit}</div>
                  </>
                )}
              </div>
              <div style={{
                margin: "16px 0 0 0", maxWidth: 260,
                fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)",
              }}>{t.desc}</div>
              <div style={{ height: 1, background: "var(--border)", margin: "24px 0" }} />
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {t.features.map((f, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <span style={{ color: "var(--success)", flex: "none", marginTop: 3 }}>
                      <CheckCircleIcon size={14} />
                    </span>
                    <div style={{ fontSize: 14, lineHeight: "20px", color: "var(--text-primary)" }}>{f}</div>
                  </div>
                ))}
              </div>
              <button style={{
                marginTop: "auto",
                height: 44,
                border: t.primary ? "none" : "1px solid var(--border-strong)",
                borderRadius: 10,
                background: t.primary ? "var(--accent)" : "var(--surface)",
                color: t.primary ? "#fff" : "var(--text-primary)",
                fontSize: 15, fontWeight: 500, cursor: "pointer",
              }}>{t.cta}</button>
            </div>
          ))}
        </div>
        <div style={{
          marginTop: 32, alignSelf: "center", textAlign: "center", maxWidth: 720,
          fontSize: 12, lineHeight: "16px", color: "var(--text-muted)",
        }}>
          All prices in INR, exclusive of GST. Volume discounts above 200 clients.
          Custom contract terms available on Enterprise.
        </div>
      </div>
    </section>
  );
}

/* --- Section 10: FAQ ---------------------------------------------------- */

function Faq() {
  const questions = [
    { q: "Do you have access to my clients' GSTN portal credentials?", open: true,
      a: "No. Niyam connects via a certified GSTN Suvidha Provider (GSP) using per-GSTIN consent flows. We never see your clients' portal login. The GSP session is scoped, time-limited, and revocable from the Settings page at any time." },
    { q: "How does the AI narrator handle sensitive client data?", open: false, a: "" },
    { q: "Can I bring my own rule pack or custom validators?",     open: false, a: "" },
    { q: "What's the difference between Growth and Enterprise?",   open: false, a: "" },
    { q: "How does data migration from Tally / Zoho / ClearTax work?", open: false, a: "" },
    { q: "Is there an on-prem or VPC deployment option?",          open: false, a: "" },
  ];
  return (
    <section style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "128px 0",
    }}>
      <div style={{ ...container, display: "flex", gap: 64, alignItems: "flex-start" }}>
        <div style={{ width: 380, flex: "none", display: "flex", flexDirection: "column" }}>
          <div style={{
            fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
            textTransform: "uppercase", color: "var(--accent)",
          }}>Frequently asked</div>
          <HeadingH2 style={{ marginTop: 16 }}>
            Answers to what CA firms ask us before they sign.
          </HeadingH2>
          <BodyLg style={{ marginTop: 24, fontSize: 15, lineHeight: "24px" }}>
            Something not covered here? Talk to a solutions engineer — we answer in under
            an hour on business days.
          </BodyLg>
          <a href="#" style={{
            marginTop: 24, fontSize: 15, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
          }}>Talk to sales →</a>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          {questions.map((it, i) => (
            <div key={i} style={{
              borderBottom: "1px solid var(--border)",
            }}>
              <div style={{
                minHeight: 72, padding: "24px 0",
                display: "flex", alignItems: "center", gap: 24, cursor: "pointer",
              }}>
                <div style={{
                  flex: 1, fontSize: 17, lineHeight: "24px", fontWeight: 500,
                  color: "var(--text-primary)",
                }}>{it.q}</div>
                <span style={{ color: "var(--text-muted)", flex: "none" }}>
                  {it.open ? <XIcon size={20} /> : <PlusIcon size={20} />}
                </span>
              </div>
              {it.open && it.a && (
                <div style={{
                  padding: "0 64px 24px 0",
                  fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)",
                  maxWidth: 640,
                }}>{it.a}</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --- Section 11: Final CTA ---------------------------------------------- */

function FinalCta() {
  return (
    <section style={{ background: "var(--bg)", padding: "128px 0" }}>
      <div style={{
        ...container, display: "flex", flexDirection: "column", alignItems: "center",
      }}>
        <div style={{
          fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--accent)",
        }}>Ready when you are</div>
        <HeadingH2 style={{ marginTop: 16, textAlign: "center", maxWidth: 800 }}>
          Ship your next GST filing with a 3-day cycle, not a 9-day one.
        </HeadingH2>
        <BodyLg style={{ marginTop: 24, textAlign: "center", maxWidth: 640 }}>
          20-minute demo. Sandbox access on day one. We&apos;ll import a real client&apos;s
          July numbers so you see it work on your own data.
        </BodyLg>
        <div style={{ marginTop: 40, display: "flex", gap: 12 }}>
          <CtaPrimary>Book a demo</CtaPrimary>
          <CtaSecondary>Read the docs ↗</CtaSecondary>
        </div>
        <div style={{ marginTop: 24, fontSize: 13, color: "var(--text-secondary)" }}>
          Prefer to try alone?{" "}
          <a href="#" style={{ fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
            Start a 14-day sandbox →
          </a>
        </div>
      </div>
    </section>
  );
}

/* --- Footer -------------------------------------------------------------- */

function Footer() {
  const cols = [
    { title: "PRODUCT",   links: ["Dashboard", "Compliance Calendar", "AI Assistant", "Contract Analysis", "Reports", "What's new ↗"] },
    { title: "SOLUTIONS", links: ["For CA firms", "For enterprises", "For compliance heads", "For growing practices", "Migrate from ClearTax", "Migrate from Tally"] },
    { title: "RESOURCES", links: ["Documentation ↗", "API reference ↗", "Security & DPA", "GST filing calendar", "Rule pack changelog", "Blog"] },
    { title: "COMPANY",   links: ["About", "Careers · (2)", "Customers", "Press kit", "Contact", "Legal"] },
  ];
  return (
    <footer style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "96px 0 48px",
    }}>
      <div style={{ ...container, display: "flex", flexDirection: "column" }}>
        <div style={{
          display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 64,
        }}>
          <div style={{ flex: 1, maxWidth: 336, display: "flex", flexDirection: "column" }}>
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
              marginTop: 16, maxWidth: 320,
              fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)",
            }}>
              The compliance workspace for India&apos;s Chartered Accountants.
            </div>
            <div style={{ marginTop: 24, display: "flex", gap: 16, color: "var(--text-muted)" }}>
              {["LI", "𝕏", "YT", "GH"].map(s => (
                <a key={s} href="#" style={{
                  width: 24, height: 24, borderRadius: 6,
                  border: "1px solid var(--border)",
                  display: "grid", placeItems: "center",
                  fontSize: 10, fontWeight: 600, color: "var(--text-secondary)",
                  textDecoration: "none",
                }}>{s}</a>
              ))}
            </div>
            <a href="#" style={{
              marginTop: 24, alignSelf: "flex-start",
              height: 32, padding: "0 12px",
              border: "1px solid var(--border)", borderRadius: 8,
              display: "inline-flex", alignItems: "center", gap: 8,
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
          <div style={{ fontSize: 11, lineHeight: "16px", color: "var(--text-muted)" }}>
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

/* --- page ---------------------------------------------------------------- */

export default function MarketingLandingPage() {
  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header />
      <Hero />
      <TrustStrip />
      <Problem />
      <ProductTour />
      <Stats />
      <Testimonials />
      <Integrations />
      <Security />
      <Pricing />
      <Faq />
      <FinalCta />
      <Footer />
    </div>
  );
}
