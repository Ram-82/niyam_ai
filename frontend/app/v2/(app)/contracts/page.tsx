import type { CSSProperties } from "react";
import {
  AlertTriangleIcon,
  ArrowUpRightIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  FileTextIcon,
  MessageSquareIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
} from "@/components/v2/icons";
type Sev = "high" | "medium" | "low";
type IssueCard = {
  n: number;
  sev: Sev;
  clause: string;
  title: string;
  category?: string;
  preview?: string;
  expanded?: boolean;
};

const ISSUES: IssueCard[] = [
  { n: 7, sev: "high", clause: "13.1", title: "Foreign governing law with full Indian tax exposure", expanded: true },
  { n: 4, sev: "high", clause: "12.2", title: "Unilateral tax gross-up shifts s.195 burden onto client", category: "Taxes", preview: "Gross-up is uncapped and survives any change in withholding rate" },
  { n: 9, sev: "high", clause: "15.4", title: "No cap on indirect or consequential damages", category: "Liability", preview: "Liability cap excludes the exact heads of loss most likely to arise" },
  { n: 6, sev: "medium", clause: "12.4", title: "Auto-renewal with only 30-day non-renewal notice", category: "Term & renewal", preview: "Notice window is shorter than the client's own budget cycle" },
  { n: 2, sev: "medium", clause: "12.3", title: "RCM applicability unclear on imported service", category: "GST", preview: "Cross-border supply: place of supply and RCM liability undefined" },
  { n: 11, sev: "low", clause: "17.2", title: "Confidentiality survives only 3 years — norm is 5", category: "Confidentiality", preview: "Shorter than the retention period for the underlying records" },
];

const MINIMAP: (Sev | "accent")[] = [
  "low", "medium", "high", "medium", "low", "high", "accent", "medium", "high", "medium", "medium", "low",
];

const sevFg: Record<Sev, string> = { high: "var(--danger)", medium: "var(--warning)", low: "var(--success)" };
const sevBg: Record<Sev, string> = { high: "var(--danger-soft)", medium: "var(--warning-soft)", low: "var(--success-soft)" };
const sevLabel: Record<Sev, string> = { high: "High", medium: "Medium", low: "Low" };

const LABEL: CSSProperties = {
  fontSize: 11,
  lineHeight: "16px",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

export default function ContractsPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0, background: "var(--bg)" }}>
      <DocHeader />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <DocViewer />
        <AnalysisPanel />
      </div>
    </div>
  );
}

/* --------------------------------- Header --------------------------------- */

function DocHeader() {
  return (
    <div
      style={{
        flex: "none",
        boxSizing: "border-box",
        borderBottom: "1px solid var(--border)",
        background: "var(--surface)",
        padding: "16px 32px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
        Documents › Contracts › August 2026
      </span>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <FileTextIcon size={20} style={{ color: "var(--text-secondary)", flex: "none" }} />
          <h1
            style={{
              margin: 0,
              fontSize: "var(--fs-h1)",
              lineHeight: "var(--lh-h1)",
              fontWeight: "var(--fw-semi)",
              letterSpacing: "var(--tr-h1)",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            Master Services Agreement — CloudMint Technologies × Ramesh Textiles Pvt Ltd
          </h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flex: "none" }}>
          <SevPill sev="high" count={3} />
          <SevPill sev="medium" count={6} />
          <SevPill sev="low" count={3} />
          <span style={{ width: 1, height: 24, background: "var(--border)" }} />
          <HeaderBtn>Export report</HeaderBtn>
          <button
            type="button"
            className="v2-btn-primary v2-focus"
            style={{
              height: 32,
              padding: "0 14px",
              border: 0,
              borderRadius: "var(--radius-input)",
              background: "var(--accent)",
              color: "var(--on-accent)",
              font: `500 13px/20px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            Share with client
          </button>
          <button
            type="button"
            aria-label="More"
            className="v2-hover-tint v2-focus"
            style={{
              width: 32, height: 32,
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
              background: "var(--surface)", color: "var(--text-secondary)",
              cursor: "pointer",
            }}
          >
            <MoreHorizontalIcon size={16} />
          </button>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <MetaChip>42 pages</MetaChip>
        <MetaChip>1.8 MB</MetaChip>
        <MetaChip>Uploaded by Priya M. · 12 Aug 2026</MetaChip>
        <MetaChip>Analyzed in 47s</MetaChip>
      </div>
    </div>
  );
}

function HeaderBtn({ children }: { children: React.ReactNode }) {
  return (
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
      {children}
    </button>
  );
}

function MetaChip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        height: 22,
        padding: "0 8px",
        display: "inline-flex",
        alignItems: "center",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-chip)",
        color: "var(--text-secondary)",
        fontSize: 11,
        fontWeight: "var(--fw-medium)",
        background: "var(--surface)",
      }}
    >
      {children}
    </span>
  );
}

function SevPill({ sev, count }: { sev: Sev; count: number }) {
  const Icon = sev === "high" ? AlertTriangleIcon : CheckCircleIcon;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        height: 26,
        padding: "0 10px",
        borderRadius: "var(--radius-pill)",
        background: sevBg[sev],
        color: sevFg[sev],
        fontSize: 12,
        fontWeight: "var(--fw-medium)",
      }}
    >
      <Icon size={12} />
      {count} {sevLabel[sev]}
    </span>
  );
}

/* --------------------------------- Document viewer --------------------------------- */

function DocViewer() {
  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--bg)", borderRight: "1px solid var(--border)" }}>
      <Toolbar />
      <div style={{ flex: 1, overflow: "auto", padding: 32, display: "flex", justifyContent: "center" }}>
        <PaperPage />
      </div>
      <Footer />
    </div>
  );
}

function Toolbar() {
  return (
    <div
      style={{
        height: 48,
        flex: "none",
        boxSizing: "border-box",
        padding: "0 16px",
        borderBottom: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <IconBtn aria-label="Previous page"><ChevronLeftIcon size={14} /></IconBtn>
        <span
          style={{
            height: 28,
            padding: "0 10px",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            color: "var(--text-secondary)",
            fontSize: 12,
            fontWeight: "var(--fw-medium)",
          }}
        >
          Page 12 of 42
          <ChevronDownIcon size={12} />
        </span>
        <IconBtn aria-label="Next page"><ChevronRightIcon size={14} /></IconBtn>
        <span style={{ width: 1, height: 20, background: "var(--border)", margin: "0 4px" }} />
        <IconBtn aria-label="Zoom out"><span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-secondary)" }}>−</span></IconBtn>
        <span className="tabular" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--text-secondary)", width: 40, textAlign: "center" }}>100%</span>
        <IconBtn aria-label="Zoom in"><PlusIcon size={14} /></IconBtn>
        <span style={{ width: 1, height: 20, background: "var(--border)", margin: "0 4px" }} />
        <div
          className="v2-search-wrap"
          style={{
            width: 240, boxSizing: "border-box", height: 28,
            display: "flex", alignItems: "center", gap: 6,
            padding: "0 8px",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-input)",
            background: "var(--bg)",
          }}
        >
          <SearchIcon size={14} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search in document"
            style={{
              flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent",
              font: `400 12px/16px var(--font-sans-v2)`, color: "var(--text-primary)",
            }}
          />
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>3 of 8</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <FilterChip selected sev="high">High</FilterChip>
        <FilterChip selected sev="medium">Medium</FilterChip>
        <FilterChip sev="low">Low</FilterChip>
        <span style={{ width: 1, height: 20, background: "var(--border)" }} />
        <IconBtn aria-label="Thumbnails"><MoreHorizontalIcon size={16} /></IconBtn>
        <IconBtn aria-label="Outline"><FileTextIcon size={16} /></IconBtn>
        <IconBtn aria-label="Download"><DownloadIcon size={16} /></IconBtn>
      </div>
    </div>
  );
}

function IconBtn({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className="v2-hover-tint v2-focus"
      style={{
        width: 28, height: 28,
        display: "flex", alignItems: "center", justifyContent: "center",
        border: 0, borderRadius: "var(--radius-chip)",
        background: "transparent",
        color: "var(--text-secondary)",
        cursor: "pointer",
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

function FilterChip({ children, selected, sev }: { children: React.ReactNode; selected?: boolean; sev: Sev }) {
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        height: 26,
        padding: "0 10px",
        borderRadius: "var(--radius-pill)",
        border: selected ? `1px solid var(--accent)` : `1px solid var(--border-strong)`,
        background: selected ? "var(--surface)" : "var(--surface)",
        color: selected ? sevFg[sev] : "var(--text-muted)",
        fontSize: 12,
        fontWeight: "var(--fw-medium)",
        cursor: "pointer",
      }}
    >
      {selected && <span style={{ width: 6, height: 6, borderRadius: "var(--radius-pill)", background: sevFg[sev] }} />}
      {children}
    </button>
  );
}

/* --------------------------------- Paper page --------------------------------- */

function PaperPage() {
  return (
    <div
      style={{
        width: "100%",
        maxWidth: 780,
        background: "var(--surface)",
        boxShadow: "var(--shadow-paper)",
        borderRadius: 4,
        padding: 56,
        display: "flex",
        flexDirection: "column",
        gap: 16,
        position: "relative",
      }}
    >
      <span style={{ fontSize: 10, color: "var(--text-muted)", textAlign: "right", marginBottom: 12 }}>
        MSA — CloudMint × Ramesh Textiles &nbsp;|&nbsp; 12
      </span>

      <h2 style={sectionHeadingStyle}>12. TAXES AND WITHHOLDING</h2>
      <p style={paraStyle}>
        <ClauseNum>12.1</ClauseNum>
        Each Party shall bear its own taxes arising under the laws applicable in its jurisdiction of
        incorporation. The Fees set out in Schedule A are exclusive of Goods and Services Tax.
      </p>
      <Highlight sev="danger" strong>
        <ClauseNum>12.2</ClauseNum>
        The Client shall gross-up all payments to the Service Provider such that the Service Provider
        receives the full invoiced amount free of any withholding, deduction, or set-off, including any
        Indian income-tax withholding under Section 195 of the Income-tax Act, 1961.
      </Highlight>
      <Highlight sev="warning">
        <ClauseNum>12.3</ClauseNum>
        Invoices shall be raised in USD.{" "}
        <strong style={{ fontWeight: 600 }}>
          GST, if applicable, shall be borne by the Client on a reverse-charge basis.
        </strong>
      </Highlight>
      <Highlight sev="warning" strong>
        <ClauseNum>12.4</ClauseNum>
        This Agreement shall renew automatically for successive one-year terms unless either Party gives
        written notice of non-renewal at least thirty (30) days prior to the end of the then-current term.
      </Highlight>

      <h2 style={{ ...sectionHeadingStyle, marginTop: 16 }}>13. GOVERNING LAW AND DISPUTE RESOLUTION</h2>
      <SelectedClause>
        <ClauseNum>13.1</ClauseNum>
        This Agreement shall be governed by and construed in accordance with the laws of Singapore. Any
        dispute arising out of or in connection with this Agreement shall be finally resolved by arbitration
        seated in Singapore under the SIAC Rules, in the English language, by a sole arbitrator.
      </SelectedClause>
      <p style={paraStyle}>
        <ClauseNum>13.2</ClauseNum>
        Nothing in this Clause 13 shall prevent either Party from seeking urgent injunctive or other interim
        relief before any court of competent jurisdiction.
      </p>
      <p style={paraStyle}>
        <ClauseNum>13.3</ClauseNum>
        The Parties shall attempt in good faith to resolve any dispute by senior-management discussion for a
        period of fifteen (15) Business Days before commencing arbitration.
      </p>
    </div>
  );
}

const sectionHeadingStyle: CSSProperties = {
  margin: 0,
  fontSize: 15,
  lineHeight: "22px",
  fontWeight: "var(--fw-semi)",
  color: "var(--text-primary)",
  letterSpacing: "0.01em",
};

const paraStyle: CSSProperties = {
  margin: 0,
  fontSize: 14,
  lineHeight: "22px",
  color: "var(--text-primary)",
};

function ClauseNum({ children }: { children: React.ReactNode }) {
  return <span style={{ fontWeight: 600, marginRight: 6 }}>{children}</span>;
}

function Highlight({ children, sev, strong }: { children: React.ReactNode; sev: "danger" | "warning"; strong?: boolean }) {
  const rail = sev === "danger" ? "var(--danger)" : "var(--warning)";
  const bg = sev === "danger" ? "var(--hl-danger)" : "var(--hl-warning)";
  return (
    <p
      style={{
        ...paraStyle,
        padding: "8px 12px",
        borderRadius: "var(--radius-chip)",
        background: bg,
        borderBottom: `3px solid ${rail}`,
        fontWeight: strong ? 500 : 400,
        cursor: "pointer",
      }}
    >
      {children}
    </p>
  );
}

function SelectedClause({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ position: "relative", paddingLeft: 16, marginLeft: 20 }}>
      <span
        style={{
          position: "absolute",
          left: -36,
          top: 0,
          height: 20,
          padding: "0 6px",
          display: "flex",
          alignItems: "center",
          border: "1px solid var(--accent)",
          borderRadius: 4,
          background: "var(--accent-soft)",
          color: "var(--accent)",
          fontSize: 11,
          fontWeight: "var(--fw-semi)",
        }}
      >
        [7]
      </span>
      <p
        style={{
          ...paraStyle,
          padding: "8px 12px",
          borderLeft: "2px solid var(--accent)",
          background: "var(--hl-danger)",
          borderBottom: "3px solid var(--danger)",
          borderRadius: "0 var(--radius-chip) var(--radius-chip) 0",
          cursor: "pointer",
        }}
      >
        {children}
      </p>
    </div>
  );
}

/* --------------------------------- Footer (minimap) --------------------------------- */

function Footer() {
  return (
    <div
      style={{
        height: 48,
        flex: "none",
        boxSizing: "border-box",
        padding: "0 16px",
        borderTop: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 24,
      }}
    >
      <span className="tabular" style={{ fontSize: 12, color: "var(--text-secondary)" }}>12 / 42</span>
      <div style={{ flex: 1, maxWidth: 520, height: 20, position: "relative", display: "flex", alignItems: "center" }}>
        <span style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: "var(--border)" }} />
        <div style={{ position: "relative", width: "100%", display: "flex", justifyContent: "space-between" }}>
          {MINIMAP.map((k, i) => (
            <MinimapMarker key={i} kind={k} />
          ))}
        </div>
      </div>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>12 flagged</span>
    </div>
  );
}

function MinimapMarker({ kind }: { kind: Sev | "accent" }) {
  if (kind === "accent") {
    return (
      <span
        style={{
          width: 10, height: 10,
          background: "var(--accent)",
          transform: "rotate(45deg)",
          border: "1.5px solid var(--surface)",
          boxShadow: "0 0 0 1px var(--accent)",
        }}
      />
    );
  }
  return (
    <span
      style={{
        width: 6, height: 6,
        borderRadius: "var(--radius-pill)",
        background: sevFg[kind],
        border: "1.5px solid var(--surface)",
        boxShadow: `0 0 0 1px ${sevFg[kind]}`,
      }}
    />
  );
}

/* --------------------------------- Analysis panel --------------------------------- */

function AnalysisPanel() {
  return (
    <aside
      style={{
        width: 640,
        flex: "none",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <TabRow />
      <SubFilterRow />
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {ISSUES.map((it) => it.expanded ? <IssueExpanded key={it.n} it={it} /> : <IssueCollapsed key={it.n} it={it} />)}
      </div>
    </aside>
  );
}

function TabRow() {
  const tabs = [
    { label: "Issues (12)", active: true },
    { label: "Summary" }, { label: "Key terms" }, { label: "Compliance" },
  ];
  return (
    <div style={{ height: 48, flex: "none", borderBottom: "1px solid var(--border)", padding: "0 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ display: "flex", alignItems: "stretch", height: "100%" }}>
        {tabs.map((t) => (
          <button
            key={t.label}
            type="button"
            className="v2-focus-inset"
            style={{
              padding: "0 14px",
              border: 0,
              background: "transparent",
              color: t.active ? "var(--text-primary)" : "var(--text-secondary)",
              font: `${t.active ? 600 : 400} 13px/20px var(--font-sans-v2)`,
              cursor: "pointer",
              boxShadow: t.active ? "inset 0 -2px 0 var(--accent)" : undefined,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="v2-btn-secondary v2-focus"
        style={{
          height: 28,
          padding: "0 10px",
          display: "flex",
          alignItems: "center",
          gap: 6,
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-input)",
          background: "var(--surface)",
          color: "var(--text-secondary)",
          font: `500 12px/16px var(--font-sans-v2)`,
          cursor: "pointer",
        }}
      >
        Sort by severity
        <ChevronDownIcon size={12} />
      </button>
    </div>
  );
}

function SubFilterRow() {
  return (
    <div style={{ height: 48, flex: "none", padding: "0 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <div
        className="v2-search-wrap"
        style={{
          width: 240, boxSizing: "border-box", height: 30,
          display: "flex", alignItems: "center", gap: 8,
          padding: "0 10px",
          border: "1px solid var(--border-strong)",
          borderRadius: "var(--radius-input)",
          background: "var(--surface)",
        }}
      >
        <SearchIcon size={14} style={{ color: "var(--text-muted)" }} />
        <input
          type="text"
          placeholder="Filter issues…"
          style={{
            flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent",
            font: `400 12px/16px var(--font-sans-v2)`, color: "var(--text-primary)",
          }}
        />
      </div>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>12 issues in 4 categories</span>
    </div>
  );
}

function SeverityChip({ sev }: { sev: Sev }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 8px",
        borderRadius: "var(--radius-chip)",
        background: sevBg[sev],
        color: sevFg[sev],
        fontSize: 11,
        fontWeight: "var(--fw-semi)",
        letterSpacing: "var(--tr-label)",
        textTransform: "uppercase",
      }}
    >
      {sevLabel[sev]}
    </span>
  );
}

function CitationBadge({ n, active }: { n: number; active?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        height: 20,
        padding: "0 6px",
        borderRadius: 4,
        background: active ? "var(--accent-soft)" : "var(--row-hover)",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        fontSize: 11,
        fontWeight: "var(--fw-semi)",
      }}
    >
      [{n}]
    </span>
  );
}

function IssueCollapsed({ it }: { it: IssueCard }) {
  return (
    <div
      style={{
        minHeight: 84,
        padding: 16,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-app-card)",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <SeverityChip sev={it.sev} />
        <CitationBadge n={it.n} />
        <span style={{ flex: 1, fontSize: 14, lineHeight: "20px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          {it.title}
        </span>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{it.clause}</span>
        <ChevronDownIcon size={14} style={{ color: "var(--text-muted)" }} />
      </div>
      {(it.category || it.preview) && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 4 }}>
          {it.category && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "2px 8px",
                borderRadius: "var(--radius-chip)",
                border: "1px solid var(--border)",
                background: "var(--bg)",
                color: "var(--text-secondary)",
                fontSize: 11,
                fontWeight: "var(--fw-medium)",
              }}
            >
              {it.category}
            </span>
          )}
          {it.preview && (
            <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {it.preview}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function IssueExpanded({ it }: { it: IssueCard }) {
  return (
    <div
      style={{
        background: "var(--row-hover-accent)",
        border: "2px solid var(--accent)",
        borderRadius: "var(--radius-app-card)",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <SeverityChip sev={it.sev} />
          <CitationBadge n={it.n} active />
          <span style={{ flex: 1, fontSize: 14, lineHeight: "20px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            {it.title}
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{it.clause}</span>
        </div>
        <div style={{ height: 1, background: "var(--border)" }} />

        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Clause excerpt</span>
          <blockquote
            style={{
              margin: 0,
              paddingLeft: 12,
              borderLeft: "3px solid var(--border-strong)",
              fontSize: 13,
              lineHeight: "22px",
              color: "var(--text-secondary)",
              maxHeight: 66,
              overflow: "hidden",
              maskImage: "linear-gradient(to bottom, black 60%, transparent 100%)",
              WebkitMaskImage: "linear-gradient(to bottom, black 60%, transparent 100%)",
            }}
          >
            This Agreement shall be governed by and construed in accordance with the laws of Singapore. Any
            dispute arising out of or in connection with this Agreement shall be finally resolved by
            arbitration seated in Singapore…
          </blockquote>
        </section>

        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Why this matters</span>
          <p style={{ margin: 0, fontSize: 13, lineHeight: "22px", color: "var(--text-primary)" }}>
            Foreign governing law and a foreign seat of arbitration for a contract performed substantially in
            India can trigger Section 9(3) complications under the A&amp;C Act and expose the Indian party to
            enforcement risk. Combined with the gross-up clause in 12.2, this shifts the entire Indian
            withholding-tax burden onto your client.
          </p>
        </section>

        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Recommendation</span>
          <p style={{ margin: 0, fontSize: 13, lineHeight: "22px", color: "var(--text-primary)" }}>
            Change governing law to Indian law and the seat of arbitration to Mumbai or Bengaluru. If a
            Singapore seat is non-negotiable, insert a carve-out preserving Indian court jurisdiction for
            interim relief.
          </p>
        </section>

        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Statutory reference</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            <StatChip>Arbitration &amp; Conciliation Act 1996, s.9(3)</StatChip>
            <StatChip>Income-tax Act, s.195</StatChip>
          </div>
        </section>
      </div>
      <div
        style={{
          height: 44,
          padding: "0 16px",
          borderTop: "1px solid var(--border)",
          background: "var(--bg)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <IconBtn aria-label="Mark reviewed"><CheckCircleIcon size={16} /></IconBtn>
          <IconBtn aria-label="Comment"><MessageSquareIcon size={16} /></IconBtn>
          <IconBtn aria-label="Assign teammate"><MoreHorizontalIcon size={16} /></IconBtn>
        </div>
        <a href="#" className="v2-focus" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>
          Jump to clause in document
          <ArrowUpRightIcon size={14} />
        </a>
      </div>
    </div>
  );
}

function StatChip({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "4px 10px",
        borderRadius: "var(--radius-chip)",
        background: "var(--accent-soft)",
        color: "var(--accent)",
        fontSize: 12,
        fontWeight: "var(--fw-medium)",
        border: 0,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
