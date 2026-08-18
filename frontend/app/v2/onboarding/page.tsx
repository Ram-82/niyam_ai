"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  SunIcon, MoonIcon, ChevronDownIcon, UploadIcon,
  FileTextIcon, XIcon, CheckCircleIcon, AlertTriangleIcon,
  SparklesIcon, SearchIcon, ArrowUpRightIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import {
  useOnboardingData,
  buildSteps,
  completedCount,
  nameFromEmail,
  initialsFrom,
  type OnboardingStep,
} from "./useOnboardingData";
import { useCsvImport, IMPORT_FIELDS, type ImportResponse } from "./useCsvImport";
import { useRef } from "react";

/* --- inline SVGs ---------------------------------------------------------- */

const CheckSvg = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 13l4 4L19 7" />
  </svg>
);

const InfoSvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={12} cy={12} r={9} />
    <path d="M12 8v.01" />
    <path d="M11 12h1v5h1" />
  </svg>
);

const PersonPlusSvg = () => (
  <svg width={20} height={20} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={9} cy={7} r={4} />
    <path d="M2 21c0-4 3-7 7-7s7 3 7 7" />
    <path d="M19 8v6M16 11h6" />
  </svg>
);

const XCircleSvg = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={12} cy={12} r={9} />
    <path d="M15 9l-6 6M9 9l6 6" />
  </svg>
);

const CompassSvg = () => (
  <svg width={12} height={12} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <circle cx={12} cy={12} r={9} />
    <path d="M15 9l-3 6-3-3z" />
  </svg>
);

/* --- data ----------------------------------------------------------------- */

type StepState = "done" | "active" | "pending";
type Step = { n: number; title: string; sub: string; state: StepState };

const STEPS: Step[] = [
  { n: 1, title: "Firm details", sub: "Acme CA · GSTIN 29AABCS1234F1Z5 · Growth plan", state: "done" },
  { n: 2, title: "Invite your team", sub: "3 invites sent · Priya, Arjun, Kavya", state: "done" },
  { n: 3, title: "Connect your GSP", sub: "WhiteBooks · sandbox connected · 2m ago", state: "done" },
  { n: 4, title: "Import your first client", sub: "Upload CSV or add manually — you can import more later", state: "active" },
  { n: 5, title: "AI narrator preference", sub: "Optional · off by default, opt-in per firm", state: "pending" },
  { n: 6, title: "You're ready", sub: "Review setup and launch your dashboard", state: "pending" },
];

type MapRow = { src: string; field: string; sample: string; mapped: boolean };
const MAPPING: MapRow[] = [
  { src: "client_name",       field: "Client name",       sample: "Ramesh Textiles Pvt Ltd, CloudMint …", mapped: true },
  { src: "gstin_primary",     field: "Primary GSTIN",     sample: "29AAAAA0000A1Z5, 27BBBBB0000B1Z2 …",  mapped: true },
  { src: "pan_no",            field: "PAN",               sample: "AAAAA0000A, BBBBB0000B …",             mapped: true },
  { src: "state_code",        field: "State (2-letter)",  sample: "KA, MH, GJ, TN, DL …",                 mapped: true },
  { src: "business_type",     field: "Business type",     sample: "Regular, SEZ, Composition …",          mapped: true },
  { src: "return_frequency",  field: "Filing frequency",  sample: "Monthly, Quarterly …",                 mapped: true },
  { src: "email_primary",     field: "Contact email",     sample: "priya@ramesh.in, …",                   mapped: true },
  { src: "phone_mobile",      field: "Contact phone",     sample: "+91 98450 12345, …",                   mapped: true },
  { src: "assigned_partner",  field: "Assigned partner",  sample: "Priya Mehta, Arjun Desai …",           mapped: true },
  { src: "onboarding_notes",  field: "—",                 sample: "Migrating from Tally; wants QRMP",     mapped: false },
  { src: "internal_tags",     field: "—",                 sample: "prio-a, textiles, karnataka …",        mapped: false },
];

type Preview = { init: string; name: string; gstin: string; state: string; type: string };
const PREVIEW: Preview[] = [
  { init: "RT", name: "Ramesh Textiles Pvt Ltd",  gstin: "29AAAAA0000A1Z5", state: "KA", type: "Regular" },
  { init: "CT", name: "CloudMint Technologies",   gstin: "27BBBBB0000B1Z2", state: "MH", type: "Regular" },
  { init: "NX", name: "Nova Exports LLP",         gstin: "24CCCCC0000C1Z9", state: "GJ", type: "SEZ" },
];

/* --- sidebar step row ----------------------------------------------------- */

function StepRow({ step, last }: { step: Step; last: boolean }) {
  const isDone = step.state === "done";
  const isActive = step.state === "active";
  const isPending = step.state === "pending";

  const nodeStyle: React.CSSProperties = isDone
    ? { background: "var(--success-soft)", color: "var(--success)" }
    : isActive
    ? { background: "var(--accent)", color: "#fff" }
    : { background: "var(--surface)", border: "2px solid var(--border-strong)", color: "var(--text-muted)" };

  return (
    <div style={{
      minHeight: last ? 44 : 72, display: "flex", gap: 12,
      opacity: isPending ? 0.6 : 1,
      background: isActive ? "#F5F7FE" : "transparent",
      boxShadow: isActive ? "inset 3px 0 0 var(--accent)" : "none",
      margin: isActive ? "-8px -24px 0 -24px" : undefined,
      padding: isActive ? "8px 24px 0 24px" : undefined,
      borderRadius: isActive ? "0 8px 8px 0" : undefined,
    }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: "none" }}>
        <div style={{
          width: 24, height: 24, borderRadius: 999,
          display: "grid", placeItems: "center",
          ...nodeStyle,
        }}>
          {isDone ? <CheckSvg size={14} /> :
           isActive ? <span style={{ width: 8, height: 8, borderRadius: 999, background: "#fff" }} /> :
           null}
        </div>
        {!last && (
          <div style={{
            flex: 1, width: 2, marginTop: 4,
            background: isDone ? "var(--success)" : "var(--border)",
            minHeight: 20,
          }} />
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingBottom: last ? 0 : 16 }}>
        <div style={{
          fontSize: 14, fontWeight: 500,
          color: isActive ? "var(--text-primary)" :
                 isDone ? "var(--text-secondary)" : "var(--text-secondary)",
        }}>
          {step.title}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
          {step.sub}
        </div>
      </div>
    </div>
  );
}

/* --- top nav -------------------------------------------------------------- */

function Nav({ theme, toggleTheme, email, onExit }: { theme: "light" | "dark"; toggleTheme: () => void; email: string | null; onExit: () => void }) {
  return (
    <div style={{
      position: "absolute", top: 32, left: 32, right: 32, zIndex: 3,
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
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {email ? `Signed in as ${email}` : "Loading account…"}
        </div>
        <div style={{ width: 1, height: 20, background: "var(--border)" }} />
        <button disabled title="Help center — coming soon" style={{
          height: 32, display: "flex", alignItems: "center", gap: 6,
          padding: "0 10px", border: "1px solid var(--border)",
          borderRadius: 8, background: "var(--surface)",
          fontSize: 12, fontWeight: 500, color: "var(--text-secondary)",
          cursor: "not-allowed", opacity: 0.5,
        }}>
          <InfoSvg size={14} /> Help ↗
        </button>
        <button onClick={onExit} style={{
          height: 32, padding: "0 12px",
          border: "1px solid var(--border)", borderRadius: 8,
          background: "var(--surface)",
          fontSize: 12, fontWeight: 500, color: "var(--text-secondary)",
          cursor: "pointer",
        }}>
          Save &amp; exit
        </button>
        <button onClick={toggleTheme}
          aria-label="Toggle theme"
          style={{
            width: 32, height: 32, border: "none", background: "transparent",
            borderRadius: 8, cursor: "pointer", color: "var(--text-secondary)",
            display: "grid", placeItems: "center",
          }}>
          {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
        </button>
      </div>
    </div>
  );
}

/* --- mapping table -------------------------------------------------------- */

function MappingTable() {
  return (
    <div style={{
      marginTop: 24, background: "var(--surface)",
      border: "1px solid var(--border)", borderRadius: 10,
      boxShadow: "0 1px 2px rgba(15,23,42,0.04)", overflow: "hidden",
    }}>
      <div style={{
        padding: "16px 20px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            Match your columns
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            Auto-detected 9 of 12 columns. Confirm or adjust before importing.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flex: "none" }}>
          <span style={{
            height: 24, display: "inline-flex", alignItems: "center", gap: 4,
            padding: "0 8px",
            background: "var(--success-soft)", color: "var(--success)",
            fontSize: 11, fontWeight: 500, borderRadius: 999,
          }}>
            <SparklesIcon size={12} /> 9 auto
          </span>
          <span style={{
            height: 24, display: "inline-flex", alignItems: "center", gap: 4,
            padding: "0 8px",
            background: "var(--warning-soft)", color: "var(--warning)",
            fontSize: 11, fontWeight: 500, borderRadius: 999,
          }}>
            <AlertTriangleIcon size={12} /> 3 need review
          </span>
        </div>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
        <colgroup>
          <col style={{ width: 220 }} />
          <col style={{ width: 240 }} />
          <col />
          <col style={{ width: 120 }} />
        </colgroup>
        <thead>
          <tr style={{ background: "var(--bg)", borderBottom: "1px solid var(--border)" }}>
            {["Source column", "Niyam field", "Sample values", "Status"].map((h, i) => (
              <th key={h} style={{
                height: 40, textAlign: "left",
                padding: i === 0 ? "0 20px" : "0 12px",
                fontSize: 11, fontWeight: 500, textTransform: "uppercase",
                letterSpacing: "0.06em", color: "var(--text-muted)",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {MAPPING.map((r, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{
                height: 56, padding: "0 20px",
                fontFamily: "var(--font-mono-v2)", fontSize: 13,
                color: "var(--text-primary)",
              }}>{r.src}</td>
              <td style={{ padding: "0 12px" }}>
                <button style={{
                  width: "100%", height: 36,
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "0 10px",
                  border: r.mapped ? "1px solid var(--border)" : "1px solid var(--border-strong)",
                  borderLeft: r.mapped ? "1px solid var(--border)" : "3px solid var(--warning)",
                  borderRadius: 8,
                  background: "var(--surface)", cursor: "pointer",
                  color: r.mapped ? "var(--text-primary)" : "var(--warning)",
                  fontSize: 13,
                }}>
                  {r.mapped ? (
                    <>
                      <span style={{
                        height: 16, padding: "0 5px",
                        display: "inline-flex", alignItems: "center",
                        background: "var(--success-soft)", color: "var(--success)",
                        fontSize: 9, fontWeight: 600, letterSpacing: "0.06em",
                        borderRadius: 3, textTransform: "uppercase",
                      }}>AUTO</span>
                      <span style={{
                        flex: 1, textAlign: "left", overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>{r.field}</span>
                      <ChevronDownIcon size={14} />
                    </>
                  ) : (
                    <span style={{ flex: 1, textAlign: "center" }}>— Select field —</span>
                  )}
                </button>
              </td>
              <td style={{
                padding: "0 12px", fontSize: 12, color: "var(--text-muted)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>{r.sample}</td>
              <td style={{ padding: "0 12px" }}>
                {r.mapped ? (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    fontSize: 12, fontWeight: 500, color: "var(--success)",
                  }}>
                    <CheckCircleIcon size={12} /> Mapped
                  </span>
                ) : (
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    fontSize: 12, fontWeight: 500, color: "var(--warning)",
                  }}>
                    <AlertTriangleIcon size={12} /> Unmapped
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{
        height: 48, padding: "0 16px 0 20px",
        background: "var(--bg)", borderTop: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
      }}>
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          9 fields mapped · 2 unmapped columns will be discarded on import
        </div>
        <a href="#" style={{ fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          Advanced: create a custom field →
        </a>
      </div>
    </div>
  );
}

/* --- preview + validation ------------------------------------------------- */

function PreviewCard() {
  return (
    <div style={{
      flex: 1, minWidth: 0, padding: 20,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{
        height: 24, display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>Preview</div>
        <a href="#" style={{ fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          View all 48 rows
        </a>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
        <colgroup>
          <col />
          <col style={{ width: 150 }} />
          <col style={{ width: 44 }} />
          <col style={{ width: 72 }} />
        </colgroup>
        <thead>
          <tr style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
            {["Name", "GSTIN", "State", "Type"].map(h => (
              <th key={h} style={{
                height: 32, padding: "0 8px", textAlign: "left",
                fontSize: 11, fontWeight: 500, textTransform: "uppercase",
                letterSpacing: "0.06em", color: "var(--text-muted)",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {PREVIEW.map((r, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ height: 40, padding: "0 8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    width: 24, height: 24, borderRadius: 6,
                    background: "var(--accent-soft)", color: "var(--accent)",
                    display: "grid", placeItems: "center",
                    fontSize: 10, fontWeight: 600,
                  }}>{r.init}</span>
                  <span style={{
                    fontSize: 13, color: "var(--text-primary)",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>{r.name}</span>
                </div>
              </td>
              <td style={{
                padding: "0 8px", fontFamily: "var(--font-mono-v2)",
                fontSize: 12, color: "var(--text-secondary)",
              }}>{r.gstin}</td>
              <td style={{ padding: "0 8px", fontSize: 11, color: "var(--text-secondary)" }}>{r.state}</td>
              <td style={{ padding: "0 8px", fontSize: 11, color: "var(--text-secondary)" }}>{r.type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValidationCard() {
  return (
    <div style={{
      flex: 1, minWidth: 0, padding: 20,
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, display: "flex", flexDirection: "column",
    }}>
      <div style={{ height: 24, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>Validation</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Ran 12s ago</div>
      </div>
      <div style={{
        minHeight: 48, marginTop: 8, display: "flex", alignItems: "center", gap: 12,
        borderBottom: "1px solid var(--border)", paddingBottom: 12,
      }}>
        <span style={{ color: "var(--success)" }}><CheckCircleIcon size={16} /></span>
        <div style={{ fontSize: 14, color: "var(--text-primary)" }}>44 rows ready to import</div>
      </div>
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "12px 0", borderBottom: "1px solid var(--border)",
      }}>
        <span style={{ color: "var(--warning)" }}><AlertTriangleIcon size={16} /></span>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{ fontSize: 14, lineHeight: "18px", color: "var(--text-primary)" }}>
            3 rows with warnings
          </div>
          <div style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
            Missing PAN — GSTIN-derived PAN will be used
          </div>
        </div>
        <a href="#" style={{ fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          Review ↗
        </a>
      </div>
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "12px 0", borderBottom: "1px solid var(--border)",
      }}>
        <span style={{ color: "var(--danger)" }}><XCircleSvg size={16} /></span>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{ fontSize: 14, lineHeight: "18px", color: "var(--text-primary)" }}>
            1 row with error
          </div>
          <div style={{ fontSize: 12, lineHeight: "16px", color: "var(--danger)" }}>
            Invalid GSTIN check digit on row 27
          </div>
        </div>
        <a href="#" style={{ fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none" }}>
          Fix ↗
        </a>
      </div>
      <div style={{
        minHeight: 48, display: "flex", alignItems: "center", gap: 12,
        paddingTop: 12,
      }}>
        <span style={{ color: "var(--text-muted)" }}><SearchIcon size={16} /></span>
        <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>0 duplicates found</div>
      </div>
    </div>
  );
}

/* --- page ---------------------------------------------------------------- */

export default function OnboardingPage() {
  const router = useRouter();
  const [method, setMethod] = useState<"csv" | "manual">("csv");
  const [theme, setTheme] = useState<"light" | "dark">("light");

  const { me, firm, clients, users, invites, gsp, loading, error, reload } = useOnboardingData();
  const importState = useCsvImport(reload);
  const steps = buildSteps(firm, clients, users, invites, gsp);
  const done = completedCount(steps);
  const progressPct = Math.round((done / steps.length) * 100);
  const firmName = firm?.name ?? null;
  const firmInitials = firmName ? initialsFrom(firmName) : "…";
  const activeStepIdx = steps.findIndex((s) => s.state === "active");
  const activeStep = activeStepIdx >= 0 ? steps[activeStepIdx] : steps[3]; // fallback: import step
  const clientCount = clients?.length ?? 0;

  const goDashboard = () => router.push("/v2/dashboard");

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    if (typeof document !== "undefined") {
      const wrap = document.querySelector<HTMLElement>('[data-theme-v="2"]');
      if (wrap) {
        if (next === "dark") wrap.setAttribute("data-theme", "dark");
        else wrap.removeAttribute("data-theme");
      }
    }
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "stretch",
      background: "var(--bg)", position: "relative",
    }}>
      <Nav theme={theme} toggleTheme={toggleTheme} email={me?.email ?? null} onExit={goDashboard} />

      {/* sidebar */}
      <aside style={{
        width: 320, flex: "none", position: "relative",
        background: "var(--surface)", borderRight: "1px solid var(--border)",
        display: "flex", flexDirection: "column", paddingTop: 96,
      }}>
        <div style={{ padding: "0 24px 24px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 10,
              background: "var(--accent-soft)", color: "var(--accent)",
              display: "grid", placeItems: "center",
              fontSize: 14, fontWeight: 600, letterSpacing: "0.02em",
            }}>{firmInitials}</div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Setting up</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
                {firmName ? `${firmName} workspace` : loading ? "Loading firm…" : "This firm"}
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: "var(--text-secondary)" }}>
            {done} of {steps.length} steps complete
          </div>
          <div style={{
            marginTop: 8, height: 4, borderRadius: 999,
            background: "var(--border)", overflow: "hidden",
          }}>
            <div style={{ width: `${progressPct}%`, height: 4, background: "var(--accent)" }} />
          </div>
        </div>
        <div style={{ padding: "24px 24px 8px", flex: 1, display: "flex", flexDirection: "column" }}>
          {steps.map((s, i) => (
            <StepRow key={s.n} step={s} last={i === steps.length - 1} />
          ))}
        </div>
        <div style={{
          height: 48, flex: "none", padding: "0 16px",
          borderTop: "1px solid var(--border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <a href="#" style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontSize: 11, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
          }}>
            <CompassSvg /> Book a setup call →
          </a>
          <a href="#" style={{
            fontSize: 11, fontWeight: 500, color: "var(--accent)", textDecoration: "none",
          }}>
            Chat with support ↗
          </a>
        </div>
      </aside>

      {/* main */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <div style={{
          flex: 1, padding: "96px 64px 32px",
        }}>
          <div style={{ maxWidth: 800, margin: "0 auto", display: "flex", flexDirection: "column" }}>
            <div style={{
              height: 24, display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div style={{
                fontSize: 11, fontWeight: 500, textTransform: "uppercase",
                letterSpacing: "0.06em", color: "var(--text-muted)",
              }}>Step {activeStep.n} of {steps.length}</div>
              <button type="button" onClick={goDashboard} style={{
                background: "transparent", border: "none", padding: 0,
                fontSize: 12, fontWeight: 500,
                color: "var(--text-secondary)", cursor: "pointer",
              }}>Skip this step for now →</button>
            </div>
            <h1 style={{
              margin: "8px 0 0 0", fontSize: 32, lineHeight: "40px",
              fontWeight: 600, letterSpacing: "-0.02em", color: "var(--text-primary)",
            }}>{activeStep.title}</h1>
            <p style={{
              margin: "12px 0 0 0", maxWidth: 640,
              fontSize: 14, lineHeight: "20px", color: "var(--text-secondary)",
            }}>
              {activeStep.sub}. Add clients from the Clients screen once you're inside — bulk CSV
              import with column mapping is on the roadmap.
            </p>

            {/* Scope notice — CSV import mechanics below are a design placeholder. */}
            <div style={{
              marginTop: 16, padding: "10px 12px",
              background: "var(--accent-soft)", color: "var(--text-primary)",
              border: "1px solid var(--accent-panel-border, var(--border))",
              borderRadius: 10, fontSize: 12, lineHeight: "18px",
              display: "flex", alignItems: "flex-start", gap: 10,
            }}>
              <span style={{ color: "var(--accent)", marginTop: 1 }}><InfoSvg size={14} /></span>
              <span>
                <strong style={{ fontWeight: 600 }}>Bulk CSV import is live.</strong>{" "}
                Upload a CSV of clients — Niyam auto-detects your columns, previews the rows, and
                reports any errors before you commit. The old design mocks (mapping table, preview
                card, validation card) have been replaced with the real flow below.
                {clientCount > 0 ? ` You already have ${clientCount} client${clientCount === 1 ? "" : "s"}.` : ""}
              </span>
            </div>

            {error && (
              <div style={{ marginTop: 12 }}>
                <ErrorBanner message={`Failed to load onboarding state — ${error}`} onRetry={reload} />
              </div>
            )}

            {/* method cards — CSV upload is live; "Add manually" still points at the Clients screen. */}
            <div style={{ marginTop: 32, display: "flex", gap: 12 }}>
              <button
                type="button"
                onClick={() => { setMethod("csv"); }}
                title="Bulk CSV upload with auto-mapping"
                style={{
                  flex: 1, minHeight: 96, padding: method === "csv" ? 16 : 17, textAlign: "left",
                  background: method === "csv" ? "var(--accent-panel-bg)" : "var(--surface)",
                  border: method === "csv" ? "2px solid var(--accent)" : "1px solid var(--border)",
                  borderRadius: 10, cursor: "pointer",
                  display: "flex", flexDirection: "column", gap: 8, position: "relative",
                }}>
                {method === "csv" && (
                  <span style={{
                    position: "absolute", top: 12, right: 12,
                    width: 8, height: 8, borderRadius: 999, background: "var(--accent)",
                  }} />
                )}
                <span style={{ color: method === "csv" ? "var(--accent)" : "var(--text-secondary)" }}>
                  <UploadIcon size={20} />
                </span>
                <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text-primary)" }}>
                  Upload CSV
                </div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  Fastest for firms migrating from Excel or another tool. Up to 5 MB per file.
                </div>
              </button>
              <button disabled title="Add clients from the Clients screen" style={{
                flex: 1, minHeight: 96, padding: method === "manual" ? 16 : 17, textAlign: "left",
                background: method === "manual" ? "var(--accent-panel-bg)" : "var(--surface)",
                border: method === "manual" ? "2px solid var(--accent)" : "1px solid var(--border)",
                borderRadius: 10, cursor: "not-allowed", opacity: 0.55,
                display: "flex", flexDirection: "column", gap: 8,
              }}>
                <span style={{ color: method === "manual" ? "var(--accent)" : "var(--text-secondary)" }}>
                  <PersonPlusSvg />
                </span>
                <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text-primary)" }}>
                  Add manually
                </div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  Add clients one at a time. Recommended if you only have a handful.
                </div>
              </button>
            </div>

            <ImportPanel state={importState} />
            {/* MappingTable / PreviewCard / ValidationCard hidden — they were
             * design mocks. Real mapping + preview + errors live inside the
             * ImportPanel above. */}

            {/* info banner */}
            <div style={{
              marginTop: 24, minHeight: 64, padding: 16,
              background: "var(--bg)",
              border: "1px solid var(--border)", borderRadius: 10,
              display: "flex", alignItems: "center", gap: 12,
            }}>
              <span style={{ color: "var(--accent)", flex: "none" }}><InfoSvg size={16} /></span>
              <div style={{ flex: 1, fontSize: 13, color: "var(--text-primary)" }}>
                Coming from Tally, Zoho Books, or ClearTax?
              </div>
              <a href="#" style={{
                fontSize: 12, fontWeight: 500, color: "var(--accent)", textDecoration: "none", flex: "none",
              }}>
                Use a pre-built importer instead ↗
              </a>
            </div>
          </div>
        </div>

        {/* sticky footer */}
        <div style={{
          height: 72, flex: "none",
          background: "var(--surface)", borderTop: "1px solid var(--border)",
          boxShadow: "0 -4px 12px rgba(15,23,42,0.04)",
          padding: "0 64px",
          display: "flex", alignItems: "center",
        }}>
          <div style={{
            maxWidth: 800, margin: "0 auto", width: "100%",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24,
          }}>
            <button type="button" onClick={goDashboard} style={{
              background: "transparent", border: "none", padding: 0,
              fontSize: 12, fontWeight: 500,
              color: "var(--text-secondary)", cursor: "pointer",
            }}>
              ← Back to dashboard
            </button>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {loading ? "Loading firm state…" : `Signed in · ${done}/${steps.length} steps complete`}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button type="button" onClick={goDashboard} style={{
                background: "transparent", border: "none", padding: 0,
                fontSize: 12, fontWeight: 500,
                color: "var(--text-secondary)", cursor: "pointer",
              }}>
                Skip this step
              </button>
              <button type="button" onClick={goDashboard} style={{
                height: 40, padding: "0 16px", position: "relative",
                display: "flex", alignItems: "center", gap: 8,
                border: "none", borderRadius: 10,
                background: "var(--accent)", color: "#fff",
                fontSize: 14, fontWeight: 500, cursor: "pointer",
              }}>
                {clientCount > 0 ? `Continue with ${clientCount} client${clientCount === 1 ? "" : "s"}` : "Continue to dashboard"}
                <ArrowUpRightIcon size={14} />
                <span style={{
                  padding: "1px 6px", borderRadius: 4,
                  background: "rgba(255,255,255,0.18)",
                  fontSize: 11, color: "rgba(255,255,255,0.85)",
                  fontFamily: "var(--font-mono-v2)",
                }}>↵</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* --------------------------------- ImportPanel ------------------------------- */

function ImportPanel({ state }: { state: ReturnType<typeof useCsvImport> }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const { file, result, loading, error, committed, pickFile, updateMapping, commit, reset } = state;

  const validRows = result ? result.total_rows - result.errors.length : 0;

  return (
    <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 16 }}>
      {/* File picker */}
      <div style={{
        minHeight: 96, padding: 20,
        background: "var(--surface)",
        border: file ? "1px solid var(--border)" : "2px dashed var(--border-strong)",
        borderRadius: 12,
        display: "flex", alignItems: "center", gap: 16,
      }}>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv,text/plain"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void pickFile(f);
            e.target.value = "";
          }}
        />
        {file ? (
          <>
            <div style={{
              width: 40, height: 40, borderRadius: 10,
              background: "var(--accent-soft)", color: "var(--accent)",
              display: "grid", placeItems: "center", flex: "none",
            }}>
              <FileTextIcon size={20} />
            </div>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{
                fontSize: 14, fontWeight: 500, color: "var(--text-primary)",
                fontFamily: "var(--font-mono-v2)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {file.name}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {result ? `${result.total_rows} rows · ${result.column_headers.length} columns` : "Reading…"}
                {" · "}{(file.size / 1024).toFixed(1)} KB
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flex: "none" }}>
              <button type="button" onClick={() => fileRef.current?.click()} style={{
                background: "transparent", border: "none",
                fontSize: 12, fontWeight: 500, color: "var(--accent)", cursor: "pointer",
              }}>Replace file</button>
              <button type="button" onClick={reset} aria-label="Remove file" style={{
                width: 32, height: 32, borderRadius: 8, border: "none",
                background: "transparent", cursor: "pointer",
                color: "var(--text-muted)", display: "grid", placeItems: "center",
              }}>
                <XIcon size={16} />
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{
              width: 40, height: 40, borderRadius: 10,
              background: "var(--row-hover)", color: "var(--text-muted)",
              display: "grid", placeItems: "center", flex: "none",
            }}>
              <UploadIcon size={20} />
            </div>
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text-primary)" }}>
                Choose a CSV to upload
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Required column: <span className="mono">trade_name</span> (or Client Name / Name / Legal name).
                Optional: gstin, state_code, scheme, language, whatsapp_number.
              </div>
            </div>
            <button type="button" onClick={() => fileRef.current?.click()} style={{
              flex: "none", height: 36, padding: "0 14px",
              border: "1px solid var(--accent)", borderRadius: 8,
              background: "var(--accent)", color: "#fff",
              fontSize: 13, fontWeight: 500, cursor: "pointer",
            }}>
              Choose file
            </button>
          </>
        )}
      </div>

      {error && <ErrorBanner message={`Import failed — ${error}`} onRetry={file ? () => void pickFile(file) : undefined} />}

      {result && (
        <>
          <MappingEditor
            headers={result.column_headers}
            mapping={result.resolved_mapping}
            onChange={(m) => void updateMapping(m)}
            disabled={loading || committed}
          />
          <ImportSummary result={result} validRows={validRows} />
          {result.errors.length > 0 && (
            <ImportErrorList title="Errors — these rows will be skipped" items={result.errors} tone="danger" />
          )}
          {result.warnings.length > 0 && (
            <ImportErrorList title="Warnings" items={result.warnings} tone="warning" />
          )}
          {!committed && validRows > 0 && (
            <button
              type="button"
              onClick={() => void commit()}
              disabled={loading}
              style={{
                alignSelf: "flex-start",
                height: 40, padding: "0 16px",
                border: "none", borderRadius: 10,
                background: "var(--accent)", color: "#fff",
                fontSize: 14, fontWeight: 500,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? "Importing…" : `Import ${validRows} client${validRows === 1 ? "" : "s"}`}
            </button>
          )}
          {committed && (
            <div style={{
              padding: "10px 14px",
              background: "var(--success-soft)", color: "var(--success)",
              border: "1px solid var(--success)", borderRadius: 10,
              fontSize: 13,
            }}>
              Imported {result.created_clients} client{result.created_clients === 1 ? "" : "s"}
              {result.created_gstins > 0 && ` (${result.created_gstins} GSTIN${result.created_gstins === 1 ? "" : "s"})`}
              . You're good to continue.
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MappingEditor({
  headers, mapping, onChange, disabled,
}: {
  headers: string[];
  mapping: Record<string, string>;
  onChange: (m: Record<string, string>) => void;
  disabled: boolean;
}) {
  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 10,
      background: "var(--surface)", overflow: "hidden",
    }}>
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid var(--border)",
        fontSize: 13, fontWeight: 500, color: "var(--text-primary)",
      }}>
        Match your columns
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
        {headers.map((h) => (
          <div key={h} style={{
            padding: "10px 16px", borderTop: "1px solid var(--border)",
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <span className="mono" style={{
              flex: 1, minWidth: 0, fontSize: 13,
              color: "var(--text-primary)",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {h}
            </span>
            <select
              value={mapping[h] ?? ""}
              disabled={disabled}
              onChange={(e) => {
                const next = { ...mapping };
                if (e.target.value) next[h] = e.target.value;
                else delete next[h];
                onChange(next);
              }}
              style={{
                flex: 1, height: 30, padding: "0 8px",
                border: "1px solid var(--border)", borderRadius: 6,
                background: "var(--surface)", color: "var(--text-primary)",
                fontSize: 12, cursor: disabled ? "not-allowed" : "pointer",
              }}
            >
              <option value="">— skip this column —</option>
              {IMPORT_FIELDS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}{f.required ? " (required)" : ""}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </div>
  );
}

function ImportSummary({ result, validRows }: { result: ImportResponse; validRows: number }) {
  return (
    <div style={{
      display: "flex", gap: 12, padding: 12,
      border: "1px solid var(--border)", borderRadius: 10, background: "var(--surface)",
    }}>
      <SummaryCell label="Total rows" value={String(result.total_rows)} />
      <SummaryCell label="Ready to import" value={String(validRows)} tone={validRows > 0 ? "var(--success)" : undefined} />
      <SummaryCell label="Errors" value={String(result.errors.length)} tone={result.errors.length > 0 ? "var(--danger)" : undefined} />
      <SummaryCell label="Warnings" value={String(result.warnings.length)} tone={result.warnings.length > 0 ? "var(--warning)" : undefined} />
    </div>
  );
}

function SummaryCell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 500 }}>
        {label}
      </span>
      <span className="tabular" style={{ fontSize: 20, fontWeight: 600, color: tone ?? "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

function ImportErrorList({ title, items, tone }: {
  title: string;
  items: { row: number; message: string }[];
  tone: "danger" | "warning";
}) {
  const bg = tone === "danger" ? "var(--danger-soft)" : "var(--warning-soft)";
  const fg = tone === "danger" ? "var(--danger)" : "var(--warning)";
  return (
    <div style={{
      padding: 12,
      background: bg,
      border: `1px solid ${fg}`,
      borderRadius: 10,
    }}>
      <div style={{
        fontSize: 12, fontWeight: 600, textTransform: "uppercase",
        letterSpacing: "0.06em", color: fg, marginBottom: 6,
      }}>
        {title} · {items.length}
      </div>
      <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, lineHeight: "20px", color: "var(--text-primary)" }}>
        {items.slice(0, 8).map((it, i) => (
          <li key={i}><strong>Row {it.row}:</strong> {it.message}</li>
        ))}
        {items.length > 8 && (
          <li style={{ color: "var(--text-muted)", listStyle: "none", marginTop: 4 }}>
            …and {items.length - 8} more
          </li>
        )}
      </ul>
    </div>
  );
}
