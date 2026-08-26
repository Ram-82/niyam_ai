"use client";

import {
  ChevronDownIcon, ArrowUpRightIcon, DownloadIcon,
  SunIcon, MoonIcon,
} from "@/components/v2/icons";

/* --- inline SVGs --------------------------------------------------------- */

const InfoSvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={12} cy={12} r={9} />
    <path d="M12 8v.01" />
    <path d="M11 12h1v5h1" />
  </svg>
);

const LinkExtSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 3h7v7M10 14 21 3M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6" />
  </svg>
);

const HashSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 9h16M4 15h16M10 3l-2 18M16 3l-2 18" />
  </svg>
);

/* --- data ---------------------------------------------------------------- */

const TOC = [
  "1. Scope and roles",
  "2. Nature of processing",
  "3. Security measures",
  "4. Sub-processors",
  "5. International transfers",
  "6. Data subject rights",
  "7. Audit rights",
  "8. Incident notification",
  "9. Data deletion & return",
  "10. Definitions",
];

const SECTION_LINKS = [
  { n: "01", title: "Scope and roles" },
  { n: "02", title: "Nature of processing" },
  { n: "03", title: "Security measures" },
];

const REMAINING_SECTIONS = [
  { n: "05", title: "International transfers" },
  { n: "06", title: "Data subject rights" },
  { n: "07", title: "Audit rights" },
  { n: "08", title: "Incident notification" },
  { n: "09", title: "Data deletion & return" },
  { n: "10", title: "Definitions" },
];

const SUBPROCESSORS = [
  { name: "Amazon Web Services (Mumbai)", purpose: "Primary hosting",           region: "IN (ap-south-1)",  data: "All customer data" },
  { name: "Anthropic PBC",                  purpose: "AI narrator (opt-in)",     region: "US",               data: "Aggregated facts (see 3.2)" },
  { name: "Google LLC (Vertex AI)",         purpose: "AI narrator alt (opt-in)", region: "IN (asia-south1)", data: "Aggregated facts" },
  { name: "WhatsApp Business API",          purpose: "Client notifications",     region: "Global (Meta)",    data: "Client contact + msg meta" },
  { name: "Postmark",                        purpose: "Transactional email",     region: "US",               data: "Email address + subject line" },
];

/* --- top nav ------------------------------------------------------------- */

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

/* --- document header ---------------------------------------------------- */

function DocHeader() {
  return (
    <section style={{ padding: "96px 0 48px", background: "var(--bg)" }}>
      <div style={{
        maxWidth: 1200, margin: "0 auto", padding: "0 32px",
        display: "flex", flexDirection: "column", gap: 20, alignItems: "flex-start",
      }}>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Legal · Data processing
        </div>
        <h1 style={{
          margin: 0, fontSize: 40, lineHeight: "48px", fontWeight: 600,
          letterSpacing: "-0.02em", color: "var(--text-primary)",
        }}>
          Data Processing Addendum
        </h1>
        <p style={{
          margin: 0, maxWidth: 720,
          fontSize: 15, lineHeight: "24px", color: "var(--text-secondary)",
        }}>
          This DPA forms part of the Master Services Agreement between Niyam AI
          Technologies Pvt Ltd and the CA firm or corporate Customer identified
          in the executed Order Form.
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <MetaBadge>Version 4.0</MetaBadge>
          <MetaBadge>Effective 15 Aug 2026</MetaBadge>
          <MetaBadge>Supersedes v3.0 (12 Feb 2026)</MetaBadge>
          <a href="#" style={{
            fontSize: 13, fontWeight: 500, color: "var(--accent)",
            textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4,
          }}>
            <DownloadIcon size={14} /> Download PDF
          </a>
          <a href="#" style={{
            fontSize: 13, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
          }}>
            See changelog ↗
          </a>
        </div>
      </div>
    </section>
  );
}

function MetaBadge({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      height: 32, padding: "0 12px",
      border: "1px solid var(--border)", borderRadius: 8,
      background: "var(--surface)",
      display: "inline-flex", alignItems: "center",
      fontSize: 12, color: "var(--text-secondary)",
    }}>{children}</span>
  );
}

/* --- TOC sidebar -------------------------------------------------------- */

function Toc() {
  const activeIndex = 3; // section 4
  return (
    <aside style={{
      width: 240, flex: "none",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, overflow: "hidden",
      position: "sticky", top: 96, alignSelf: "flex-start",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{
        height: 48, padding: "0 20px",
        borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center",
        fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
        textTransform: "uppercase", color: "var(--text-muted)",
      }}>
        On this page
      </div>
      <div style={{
        flex: 1, padding: "16px 0",
        display: "flex", flexDirection: "column",
      }}>
        {TOC.map((label, i) => {
          const active = i === activeIndex;
          return (
            <a key={label} href={`#section-${i + 1}`} style={{
              height: 32, padding: "0 16px",
              display: "flex", alignItems: "center",
              textDecoration: "none",
              background: active ? "#F5F7FE" : "transparent",
              boxShadow: active ? "inset 3px 0 0 var(--accent)" : "none",
              fontSize: 13,
              color: active ? "var(--accent)" : "var(--text-secondary)",
              fontWeight: active ? 500 : 400,
            }}>{label}</a>
          );
        })}
      </div>
      <div style={{
        height: 48, padding: "0 16px", flex: "none",
        borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          Last updated 15 Aug 2026
        </span>
        <a href="#" style={{
          fontSize: 11, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
        }}>Report ↗</a>
      </div>
    </aside>
  );
}

/* --- section link row ---------------------------------------------------- */

function SectionLink({ n, title }: { n: string; title: string }) {
  return (
    <a href={`#section-${parseInt(n)}`} style={{
      height: 56, padding: "0 4px",
      borderTop: "1px solid var(--border)",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      textDecoration: "none",
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{
          fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>Section {n}</div>
        <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>{title}</div>
      </div>
      <span style={{ color: "var(--text-muted)" }}><LinkExtSvg /></span>
    </a>
  );
}

/* --- section 4 body (expanded) ------------------------------------------ */

function Section4() {
  return (
    <section id="section-4" style={{
      paddingTop: 24, borderTop: "1px solid var(--border)", marginTop: 24,
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 8,
      }}>
        <div style={{
          fontSize: 11, fontWeight: 500, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>Section 04</div>
        <button aria-label="Copy anchor link" style={{
          width: 28, height: 28, border: "none", background: "transparent",
          borderRadius: 6, cursor: "pointer", color: "var(--text-muted)",
          display: "grid", placeItems: "center",
        }}>
          <HashSvg />
        </button>
      </div>
      <h2 style={{
        margin: 0, fontSize: 24, lineHeight: "32px", fontWeight: 600,
        letterSpacing: "-0.01em", color: "var(--text-primary)",
      }}>
        4. Sub-processors
      </h2>

      <p style={{
        margin: "16px 0 0 0", fontSize: 17, lineHeight: "28px", color: "var(--text-primary)",
      }}>
        <strong style={{ color: "var(--text-muted)", fontWeight: 500, marginRight: 8 }}>4.1</strong>
        Customer authorises Niyam AI to engage the sub-processors listed in Annex A
        of this DPA to process Personal Data on Customer&apos;s behalf. Niyam AI will
        remain fully liable for the acts and omissions of any sub-processor to the
        same extent as for its own acts and omissions.
      </p>
      <p style={{
        margin: "16px 0 0 0", fontSize: 17, lineHeight: "28px", color: "var(--text-primary)",
      }}>
        <strong style={{ color: "var(--text-muted)", fontWeight: 500, marginRight: 8 }}>4.2</strong>
        Niyam AI will notify Customer at least thirty (30) days in advance of any
        addition to, or replacement of, an existing sub-processor. Customer may
        object to any such change in writing within fifteen (15) days of notice.
      </p>
      <p style={{
        margin: "16px 0 0 0", fontSize: 17, lineHeight: "28px", color: "var(--text-primary)",
      }}>
        <strong style={{ color: "var(--text-muted)", fontWeight: 500, marginRight: 8 }}>4.3</strong>
        Where Customer&apos;s objection cannot be reasonably resolved within thirty (30)
        days, Customer may terminate the affected Services in accordance with the
        MSA and receive a pro rata refund of pre-paid fees for the terminated portion.
      </p>

      <h3 style={{
        margin: "32px 0 0 0", fontSize: 17, lineHeight: "24px", fontWeight: 600,
        color: "var(--text-primary)",
      }}>
        Annex A — Approved sub-processors
      </h3>

      <div style={{
        marginTop: 16, background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: 10,
        boxShadow: "0 1px 2px rgba(15,23,42,0.04)", overflow: "hidden",
      }}>
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: "30%" }} />
            <col style={{ width: "26%" }} />
            <col style={{ width: "20%" }} />
            <col style={{ width: "24%" }} />
          </colgroup>
          <thead>
            <tr style={{ background: "var(--bg)", borderBottom: "1px solid var(--border)" }}>
              {["Sub-processor", "Purpose", "Region", "Category of data"].map(h => (
                <th key={h} style={{
                  height: 40, padding: "0 16px", textAlign: "left",
                  fontSize: 11, fontWeight: 500, textTransform: "uppercase",
                  letterSpacing: "0.06em", color: "var(--text-muted)",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SUBPROCESSORS.map((s, i) => (
              <tr key={s.name} style={{
                borderBottom: i < SUBPROCESSORS.length - 1 ? "1px solid var(--border)" : "none",
              }}>
                <td style={{
                  height: 56, padding: "0 16px",
                  fontSize: 14, fontWeight: 500, color: "var(--text-primary)",
                }}>{s.name}</td>
                <td style={{
                  padding: "0 16px",
                  fontSize: 13, color: "var(--text-secondary)",
                }}>{s.purpose}</td>
                <td style={{
                  padding: "0 16px",
                  fontSize: 13, color: "var(--text-secondary)",
                  fontFamily: "var(--font-mono-v2)",
                }}>{s.region}</td>
                <td style={{
                  padding: "0 16px",
                  fontSize: 13, color: "var(--text-secondary)",
                }}>{s.data}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{
        marginTop: 24, padding: 20, borderRadius: 10,
        background: "var(--accent-panel-bg)",
        border: "1px solid var(--accent-panel-border)",
        borderLeft: "3px solid var(--accent)",
        display: "flex", gap: 12,
      }}>
        <span style={{ color: "var(--accent)", flex: "none", marginTop: 2 }}>
          <InfoSvg size={18} />
        </span>
        <div>
          <div style={{
            fontSize: 18, lineHeight: "28px", fontWeight: 600, color: "var(--text-primary)",
          }}>Objection process</div>
          <div style={{
            marginTop: 8, fontSize: 15, lineHeight: "24px", color: "var(--text-primary)",
          }}>
            Send objections to{" "}
            <a href="mailto:privacy@niyam.ai" style={{
              color: "var(--accent)", textDecoration: "none", fontWeight: 500,
            }}>privacy@niyam.ai</a>{" "}
            with the subject line &quot;Sub-processor objection&quot;. We acknowledge within
            3 business days and respond substantively within 15 days.
          </div>
        </div>
      </div>
    </section>
  );
}

/* --- feedback + related ------------------------------------------------- */

function FeedbackRow() {
  return (
    <div style={{
      marginTop: 48, paddingTop: 32, borderTop: "1px solid var(--border)",
      display: "flex", flexDirection: "column", gap: 20,
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
      }}>
        <div style={{ fontSize: 15, color: "var(--text-secondary)" }}>
          Was this page clear?
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={{
            height: 32, padding: "0 16px",
            border: "1px solid var(--border)", borderRadius: 8,
            background: "var(--surface)", color: "var(--text-primary)",
            fontSize: 12, fontWeight: 500, cursor: "pointer",
          }}>Yes</button>
          <button style={{
            height: 32, padding: "0 16px",
            border: "1px solid var(--border)", borderRadius: 8,
            background: "var(--surface)", color: "var(--text-primary)",
            fontSize: 12, fontWeight: 500, cursor: "pointer",
          }}>No</button>
        </div>
      </div>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <a href="#" style={{ fontSize: 13, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          Read the Privacy Policy →
        </a>
        <a href="#" style={{ fontSize: 13, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          Read the MSA →
        </a>
        <a href="#" style={{ fontSize: 13, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          Read the Security page →
        </a>
      </div>
    </div>
  );
}

/* --- footer -------------------------------------------------------------- */

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

/* --- page ---------------------------------------------------------------- */

export default function LegalDpaPage() {
  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header />
      <DocHeader />
      <div style={{
        maxWidth: 1200, margin: "0 auto", padding: "0 32px 48px",
        display: "flex", gap: 64, alignItems: "flex-start",
      }}>
        <Toc />
        <main style={{ flex: 1, minWidth: 0, maxWidth: 800 }}>
          {SECTION_LINKS.map(s => <SectionLink key={s.n} n={s.n} title={s.title} />)}
          <Section4 />
          {REMAINING_SECTIONS.map(s => <SectionLink key={s.n} n={s.n} title={s.title} />)}
          <FeedbackRow />
        </main>
      </div>
      <Footer />
    </div>
  );
}
