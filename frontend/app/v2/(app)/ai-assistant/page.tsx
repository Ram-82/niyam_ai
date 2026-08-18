"use client";

import { useState, type CSSProperties } from "react";
import {
  ArrowUpIcon,
  ArrowUpRightIcon,
  ChevronRightIcon,
  DownloadIcon,
  MoreHorizontalIcon,
  PlusIcon,
  SearchIcon,
  XIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { LoadingState } from "@/components/v2/ui/LoadingState";
import {
  downloadNarrationPdf,
  formatPeriod,
  formatRelative,
  groupRuns,
  prettyReturnType,
  useNarratorRuns,
  type ConvoGroup,
  type NarrationRunRow,
} from "./useNarratorData";

type Convo = { title: string; preview: string; active?: boolean };
const CONVOS: { label: string; items: Convo[] }[] = [
  { label: "Today", items: [
    { title: "ITC on employee food coupons", preview: "…blocked under Section 17(5)(b)(i)…", active: true },
    { title: "Section 194Q applicability FY25-26", preview: "Turnover above ₹10 Cr — buyer liable…" },
    { title: "GSTR-9C reconciliation threshold", preview: "₹5 Cr aggregate turnover, FY 2025-26…" },
  ] },
  { label: "Yesterday", items: [
    { title: "AOC-4 XBRL filing exemption", preview: "Applicability to unlisted public companies…" },
    { title: "TDS on payments to non-residents", preview: "Section 195 rates and DTAA overlay…" },
  ] },
  { label: "Last 7 days", items: [
    { title: "Reverse charge on legal fees", preview: "Advocate services to business entity…" },
    { title: "E-invoice turnover threshold 2026", preview: "₹5 Cr aggregate turnover · effective 1 Aug…" },
  ] },
];

type SourceCard = {
  active?: boolean;
  type: string;
  typeTone: "accent" | "warning" | "neutral";
  title: string;
  citation: string;
  extract?: string;
};
const SOURCES: SourceCard[] = [
  {
    active: true,
    type: "CGST Act",
    typeTone: "accent",
    title: "Section 17(5)(b)(i)",
    citation: "Amended by Finance Act 2023",
    extract:
      "Notwithstanding anything contained in sub-section (1) of section 16 and sub-section (1) of section 18, input tax credit shall not be available in respect of the following, namely:— (b) the following supply of goods or services or both — (i) food and beverages, outdoor catering, beauty treatment, health services…",
  },
  {
    type: "Circular",
    typeTone: "warning",
    title: "Circular No. 172/04/2022-GST",
    citation: "6 Jul 2022 · CBIC · 4 pages",
    extract: "…the words 'obligatory under a law' shall be construed strictly…",
  },
  {
    type: "AAR Ruling",
    typeTone: "neutral",
    title: "KAR/AAR/23/2023 — Musigma Business Solutions",
    citation: "12 Sep 2023 · Karnataka AAR · Related to Sec 17(5)",
    extract: "Karnataka AAR ruled food coupons issued to employees are not eligible for ITC…",
  },
  {
    type: "Case Law",
    typeTone: "neutral",
    title: "M/s Bharti Airtel Ltd v. Union of India",
    citation: "28 Oct 2021 · Supreme Court · Civil Appeal 6520/2021",
    extract: "SC clarified scope of blocked credits and burden of proof…",
  },
];

const SUMMARY_CARDS = [
  { type: "CGST Act", tone: "accent" as const, title: "Section 17(5)(b)", desc: "Blocked credits →" },
  { type: "Circular", tone: "warning" as const, title: "172/04/2022-GST", desc: "Clarification on Sec 17(5) →" },
  { type: "AAR Ruling", tone: "neutral" as const, title: "KAR/AAR/23/2023", desc: "Karnataka — food coupons →" },
  { type: "Case Law", tone: "neutral" as const, title: "Bharti Airtel v. UOI", desc: "SC — blocked credits →" },
];

const LABEL: CSSProperties = {
  fontSize: 11,
  lineHeight: "16px",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

export default function AiAssistantPage() {
  const { runs, loading, error, reload } = useNarratorRuns();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const active =
    (runs ?? []).find((r) => r.id === selectedId) ?? (runs?.[0] ?? null);
  const groups = groupRuns(runs ?? [], active?.id ?? null);

  return (
    <div style={{ display: "flex", flex: 1, minWidth: 0, minHeight: 0, background: "var(--bg)" }}>
      <ConversationsRail
        groups={groups}
        loading={loading && runs === null}
        error={error}
        onRetry={reload}
        onSelect={setSelectedId}
      />
      <ChatColumn active={active} loading={loading && runs === null} />
      <SourcesPanel active={active} />
    </div>
  );
}

/* --------------------------------- Conversations rail --------------------------------- */

function ConversationsRail({
  groups, loading, error, onRetry, onSelect,
}: {
  groups: ConvoGroup[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <aside
      style={{
        width: 240,
        flex: "none",
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div style={{ height: 48, padding: "0 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0, fontSize: 15, lineHeight: "20px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          Conversations
        </h2>
        <button
          type="button"
          aria-label="New conversation"
          className="v2-hover-tint v2-focus"
          style={{
            width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "1px solid var(--accent)",
            borderRadius: "var(--radius-input)",
            background: "transparent",
            color: "var(--accent)",
            cursor: "pointer",
          }}
        >
          <PlusIcon size={14} />
        </button>
      </div>
      <div style={{ padding: "12px 12px 8px" }}>
        <div
          className="v2-search-wrap"
          style={{
            boxSizing: "border-box",
            height: 32,
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 10px",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-input)",
            background: "var(--bg)",
          }}
        >
          <SearchIcon size={14} style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            placeholder="Search conversations…"
            style={{
              flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent",
              font: `400 12px/16px var(--font-sans-v2)`, color: "var(--text-primary)",
            }}
          />
        </div>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: "0 8px 8px" }}>
        {error && (
          <div style={{ padding: "8px" }}>
            <ErrorBanner message={`Could not load runs: ${error}`} onRetry={onRetry} />
          </div>
        )}
        {loading && groups.length === 0 && !error && (
          <LoadingState variant="inline" />
        )}
        {!loading && !error && groups.length === 0 && (
          <EmptyState variant="inline" message="No narration runs yet." hint="Generate one from a filing to see it here." />
        )}
        {groups.map((g) => (
          <div key={g.label} style={{ marginBottom: 8 }}>
            <div style={{ padding: "8px 8px 4px", ...LABEL }}>{g.label}</div>
            {g.items.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelect(c.id)}
                className={c.active ? "v2-focus" : "v2-nav-link v2-focus"}
                style={{
                  position: "relative",
                  display: "flex",
                  flexDirection: "column",
                  gap: 2,
                  padding: "8px 12px",
                  width: "100%",
                  border: 0,
                  borderRadius: "var(--radius-input)",
                  background: c.active ? "var(--accent-soft)" : "transparent",
                  color: c.active ? "var(--accent)" : "var(--text-primary)",
                  textDecoration: "none",
                  boxShadow: c.active ? "inset 3px 0 0 var(--accent)" : undefined,
                  cursor: "pointer",
                  textAlign: "left",
                  font: "inherit",
                }}
              >
                <span style={{ fontSize: 13, fontWeight: "var(--fw-medium)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {c.title}
                </span>
                <span style={{ fontSize: 11, color: c.active ? "var(--accent)" : "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", opacity: c.active ? 0.8 : 1 }}>
                  {c.preview}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
      <div style={{ height: 48, padding: "0 16px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--text-secondary)", textDecoration: "none" }}>
          Archived (12)
        </a>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>2.1 GB / 10 GB</span>
      </div>
    </aside>
  );
}

/* --------------------------------- Chat column --------------------------------- */

function ChatColumn({ active, loading }: { active: NarrationRunRow | null; loading: boolean }) {
  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <ChatHeader active={active} />
      <div style={{ flex: 1, overflow: "auto", padding: "24px 32px", display: "flex", justifyContent: "flex-start" }}>
        <div style={{ maxWidth: 760, width: "100%", display: "flex", flexDirection: "column", gap: 24 }}>
          <ScopeNotice />
          {loading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading conversations…</div>
          ) : active ? (
            <NarrationRunView run={active} />
          ) : (
            <div style={{
              padding: 24,
              border: "1px dashed var(--border-strong)",
              borderRadius: "var(--radius-app-card)",
              background: "var(--surface)",
              color: "var(--text-secondary)",
              fontSize: 13, lineHeight: "20px",
            }}>
              Select a narration on the left, or open a filing and click <strong style={{ fontWeight: 500 }}>Generate narration</strong> to create one.
            </div>
          )}
        </div>
      </div>
      <InputDock />
    </div>
  );
}

function ScopeNotice() {
  return (
    <div style={{
      padding: "10px 14px",
      border: "1px solid var(--accent-panel-border)",
      borderLeft: "3px solid var(--accent)",
      background: "var(--accent-panel-bg)",
      borderRadius: "var(--radius-app-card)",
      color: "var(--text-primary)",
      fontSize: 12, lineHeight: "18px",
    }}>
      <strong style={{ fontWeight: 500 }}>Q&amp;A coming soon.</strong> Today this pane shows narration runs the firm has generated for GSTR-1 / GSTR-3B filings. Free-form legal Q&amp;A ships with the next backend release.
    </div>
  );
}

function NarrationRunView({ run }: { run: NarrationRunRow }) {
  const onDownload = () => {
    downloadNarrationPdf(run.id).catch((e) => {
      alert(`Download failed: ${e?.message ?? e}`);
    });
  };
  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-app-card)",
      boxShadow: "var(--shadow-card)",
      padding: 20,
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
            {prettyReturnType(run.return_type)} · {formatPeriod(run.period)}
          </span>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Generated {formatRelative(run.generated_at)} · GSTIN {run.gstin_profile_id.slice(0, 8)}…
          </span>
        </div>
        <button
          type="button"
          onClick={onDownload}
          className="v2-btn-primary v2-focus"
          style={{
            height: 32, display: "flex", alignItems: "center", gap: 6,
            padding: "0 12px", border: 0, borderRadius: "var(--radius-input)",
            background: "var(--accent)", color: "var(--on-accent)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          <DownloadIcon size={14} />
          Download PDF
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 12px", fontSize: 12 }}>
        <span style={{ color: "var(--text-muted)" }}>Provider</span>
        <span style={{ color: "var(--text-primary)" }}>{run.provider}</span>
        <span style={{ color: "var(--text-muted)" }}>Model</span>
        <span className="mono" style={{ color: "var(--text-primary)" }}>{run.model}</span>
        <span style={{ color: "var(--text-muted)" }}>Language</span>
        <span style={{ color: "var(--text-primary)" }}>{run.language.toUpperCase()}</span>
      </div>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
        Full narration body isn&apos;t returned by <span className="mono">/narrator/runs</span> — open the PDF for the four-section text (client health, tax position, attention, ask-your-CA).
      </span>
    </div>
  );
}

function ChatHeader({ active }: { active: NarrationRunRow | null }) {
  return (
    <div
      style={{
        height: 56,
        flex: "none",
        padding: "0 24px",
        borderBottom: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
      }}
    >
      <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {active ? `${prettyReturnType(active.return_type)} narration · ${formatPeriod(active.period)}` : "AI Assistant"}
      </h2>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            height: 28, padding: "0 10px",
            border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
            background: "var(--surface)", color: "var(--text-secondary)",
            fontSize: 12, fontWeight: "var(--fw-medium)",
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: "var(--radius-pill)", background: active ? "var(--accent)" : "var(--text-muted)" }} />
          {active ? `${active.provider} · ${active.model}` : "No conversation selected"}
        </span>
        <SmallGhost aria-label="Share"><ArrowUpRightIcon size={14} /></SmallGhost>
        <SmallGhost aria-label="More"><MoreHorizontalIcon size={16} /></SmallGhost>
      </div>
    </div>
  );
}

function SmallGhost({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
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

function UserMessage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
      <div
        style={{
          maxWidth: 520,
          background: "var(--accent-soft)",
          color: "var(--text-primary)",
          borderRadius: 10,
          padding: "12px 16px",
          fontSize: 14,
          lineHeight: "22px",
        }}
      >
        Is input tax credit available on food coupons (Sodexo, Zeta) given to employees as part of CTC?
        Client is a Karnataka IT services company, FY 2025-26.
      </div>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Today, 11:42 AM</span>
    </div>
  );
}

function AiResponse() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <VerdictStrip />
      <SummaryParagraph />
      <StatutoryAnalysisCard />
      <SourceCardsRow />
      <ActionRow />
      <FollowUpChips />
    </div>
  );
}

function VerdictStrip() {
  return (
    <div
      style={{
        minHeight: 48,
        padding: "12px 16px",
        background: "var(--danger-soft)",
        borderLeft: "3px solid var(--danger)",
        borderRadius: "0 var(--radius-chip) var(--radius-chip) 0",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      <XCircleSvg />
      <span style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--danger)" }}>
        Not eligible
      </span>
      <span style={{ color: "var(--text-muted)" }}>·</span>
      <span style={{ fontSize: 13, color: "var(--text-primary)" }}>
        Blocked u/s 17(5)(b)(i) of CGST Act
      </span>
    </div>
  );
}

function XCircleSvg() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </svg>
  );
}

function Cite({ n }: { n: number }) {
  return (
    <button
      type="button"
      className="v2-focus tabular"
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 20,
        padding: "0 6px",
        margin: "0 2px",
        borderRadius: 4,
        background: "var(--accent-soft)",
        color: "var(--accent)",
        fontSize: 11,
        fontWeight: "var(--fw-semi)",
        border: 0,
        cursor: "pointer",
        verticalAlign: "middle",
      }}
    >
      [{n}]
    </button>
  );
}

function SummaryParagraph() {
  return (
    <p style={{ margin: 0, fontSize: 14, lineHeight: "22px", color: "var(--text-primary)" }}>
      ITC on food and beverages supplied to employees is blocked under Section 17(5)(b)(i) of the CGST
      Act, 2017<Cite n={1} />. The exception in the proviso — where the supply is obligatory under a law
      in force — does not apply to a private IT services company issuing food coupons as part of CTC,
      since no such statutory obligation exists for this employer class<Cite n={2} />.
    </p>
  );
}

function StatutoryAnalysisCard() {
  const rows: { cond: string; outcome: { label: string; tone: "neutral" | "danger" }; note: string }[] = [
    { cond: "Nature of supply", outcome: { label: "Food & beverage", tone: "neutral" }, note: "Composite supply to employees" },
    { cond: "Blocking clause", outcome: { label: "Sec 17(5)(b)(i)", tone: "danger" }, note: "Absolute bar unless proviso applies" },
    { cond: "Proviso available?", outcome: { label: "No", tone: "danger" }, note: "No statutory obligation for private IT" },
  ];
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-app-card)",
        boxShadow: "var(--shadow-card)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <span style={LABEL}>Statutory analysis</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((r) => (
          <div key={r.cond} style={{ display: "grid", gridTemplateColumns: "140px auto 1fr", gap: 12, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{r.cond}</span>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "3px 8px",
                borderRadius: "var(--radius-chip)",
                fontSize: 11,
                fontWeight: "var(--fw-medium)",
                ...(r.outcome.tone === "danger"
                  ? { background: "var(--danger-soft)", color: "var(--danger)" }
                  : { background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)" }),
              }}
            >
              {r.outcome.label}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{r.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SourceCardsRow() {
  return (
    <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 4 }}>
      {SUMMARY_CARDS.map((c) => (
        <div
          key={c.title}
          style={{
            width: 220,
            height: 108,
            flex: "none",
            padding: 12,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-app-card)",
            display: "flex",
            flexDirection: "column",
            gap: 6,
            cursor: "pointer",
          }}
        >
          <TypeChip tone={c.tone}>{c.type}</TypeChip>
          <span style={{ fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {c.title}
          </span>
          <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }}>{c.desc}</span>
        </div>
      ))}
    </div>
  );
}

function TypeChip({ tone, children }: { tone: "accent" | "warning" | "neutral"; children: React.ReactNode }) {
  const style: CSSProperties =
    tone === "accent" ? { background: "var(--accent-soft)", color: "var(--accent)" } :
    tone === "warning" ? { background: "var(--warning-soft)", color: "var(--warning)" } :
    { background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border)" };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        alignSelf: "flex-start",
        padding: "2px 8px",
        borderRadius: "var(--radius-chip)",
        fontSize: 11,
        fontWeight: "var(--fw-medium)",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

function ActionRow() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <ActionBtn aria-label="Helpful"><ThumbsUpSvg /></ActionBtn>
      <ActionBtn aria-label="Not helpful"><ThumbsDownSvg /></ActionBtn>
      <ActionBtn aria-label="Copy"><CopySvg /></ActionBtn>
      <ActionBtn aria-label="Regenerate"><RegenSvg /></ActionBtn>
      <ActionBtn aria-label="Share"><ArrowUpRightIcon size={14} /></ActionBtn>
      <span style={{ flex: 1 }} />
      <span style={{ fontSize: 11, color: "var(--text-muted)" }} className="tabular">Answered in 3.2s · 4 sources</span>
    </div>
  );
}

function ActionBtn({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className="v2-hover-tint v2-focus"
      style={{
        width: 28, height: 28,
        display: "flex", alignItems: "center", justifyContent: "center",
        border: 0, borderRadius: "var(--radius-chip)",
        background: "transparent",
        color: "var(--text-muted)",
        cursor: "pointer",
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

function ThumbsUpSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 22V11l5-8 1 .5c.7.4 1 1.2 1 2V9h6a2 2 0 0 1 2 2l-2 8a3 3 0 0 1-3 2z" />
    </svg>
  );
}
function ThumbsDownSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ transform: "rotate(180deg)" }}>
      <path d="M7 22V11l5-8 1 .5c.7.4 1 1.2 1 2V9h6a2 2 0 0 1 2 2l-2 8a3 3 0 0 1-3 2z" />
    </svg>
  );
}
function CopySvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  );
}
function RegenSvg() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 4v5h-5" />
    </svg>
  );
}

function FollowUpChips() {
  const chips = [
    "What if food is supplied in a factory canteen under Factories Act?",
    "Draft an internal note explaining this to the finance team",
    "Show all AAR rulings on 17(5) from last 3 years",
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {chips.map((c) => (
        <button
          key={c}
          type="button"
          className="v2-focus"
          style={{
            height: 32,
            padding: "0 12px",
            display: "flex",
            alignItems: "center",
            gap: 6,
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--surface)",
            color: "var(--text-secondary)",
            font: `400 13px/20px var(--font-sans-v2)`,
            cursor: "pointer",
            alignSelf: "flex-start",
          }}
        >
          <ChevronRightIcon size={12} style={{ color: "var(--text-muted)" }} />
          {c}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------- Input dock --------------------------------- */

function InputDock() {
  return (
    <div style={{ flex: "none", padding: "12px 32px 20px", borderTop: "1px solid var(--border)", background: "var(--surface)", display: "flex", flexDirection: "column", gap: 6, alignItems: "center" }}>
      <div style={{ width: "100%", maxWidth: 760, display: "flex", flexDirection: "column", gap: 6 }}>
        <div
          style={{
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-app-card)",
            background: "var(--surface)",
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <textarea
            rows={3}
            disabled
            placeholder="Free-form Q&A coming soon. For now, generate a narration from a filing to see it appear at left."
            style={{
              width: "100%",
              minHeight: 72,
              border: 0,
              outline: 0,
              resize: "none",
              background: "transparent",
              font: `400 14px/22px var(--font-sans-v2)`,
              color: "var(--text-muted)",
              cursor: "not-allowed",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <SmallGhost aria-label="Attach document"><PaperclipSvg /></SmallGhost>
            <SmallGhost aria-label="Attach image"><ImageSvg /></SmallGhost>
            <SmallGhost aria-label="Reference client"><AtSvg /></SmallGhost>
            <span style={{ flex: 1 }} />
            <DockChip>Legal research</DockChip>
            <DockChip>GPT-4 · Legal</DockChip>
            <button
              type="button"
              aria-label="Send"
              disabled
              title="Free-form Q&A coming soon"
              className="v2-btn-primary v2-focus"
              style={{
                width: 32, height: 32,
                display: "flex", alignItems: "center", justifyContent: "center",
                border: 0, borderRadius: "var(--radius-input)",
                background: "var(--accent)",
                color: "var(--on-accent)",
                cursor: "not-allowed",
                opacity: 0.5,
              }}
            >
              <ArrowUpIcon size={14} />
            </button>
          </div>
        </div>
        <span style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center" }}>
          Niyam AI cites primary sources but is not a substitute for professional advice. Verify before filing.
        </span>
      </div>
    </div>
  );
}

function DockChip({ children }: { children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="v2-btn-secondary v2-focus"
      style={{
        height: 28,
        display: "flex",
        alignItems: "center",
        gap: 4,
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
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
    </button>
  );
}

function PaperclipSvg() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 10.5 11 20a5.5 5.5 0 0 1-8-7.5L12 3a4 4 0 0 1 5.6 5.6L9 17a2.5 2.5 0 0 1-3.5-3.5L13 6" />
    </svg>
  );
}
function ImageSvg() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.5" />
      <path d="m21 17-5-5-9 9" />
    </svg>
  );
}
function AtSvg() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" />
    </svg>
  );
}

/* --------------------------------- Sources panel --------------------------------- */

function SourcesPanel({ active: _active }: { active: NarrationRunRow | null }) {
  // NOTE: sources/citations are demo-only. The narrator endpoint doesn't
  // return per-run citations; wiring pending a citations model.
  return SourcesPanelInner();
}

function SourcesPanelInner() {
  return (
    <aside
      style={{
        width: 360,
        flex: "none",
        background: "var(--surface)",
        borderLeft: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div style={{ height: 56, padding: "0 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Sources</h2>
          <span style={{ padding: "1px 8px", borderRadius: "var(--radius-pill)", background: "var(--row-hover)", color: "var(--text-secondary)", fontSize: 12, fontWeight: "var(--fw-semi)" }}>4</span>
        </div>
        <SmallGhost aria-label="Collapse"><XIcon size={14} /></SmallGhost>
      </div>
      <div style={{ height: 48, padding: "0 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 6, overflowX: "auto" }}>
        <SrcChip active>All 4</SrcChip>
        <SrcChip>Acts 1</SrcChip>
        <SrcChip>Rules 0</SrcChip>
        <SrcChip>Circulars 1</SrcChip>
        <SrcChip>Cases 2</SrcChip>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {SOURCES.map((s, i) => <SrcCard key={i} s={s} />)}
      </div>
      <div style={{ padding: "12px 16px 16px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
        <button
          type="button"
          className="v2-btn-secondary v2-focus"
          style={{
            width: "100%",
            height: 36,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
            border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
            background: "var(--surface)", color: "var(--text-primary)",
            font: `500 13px/20px var(--font-sans-v2)`, cursor: "pointer",
          }}
        >
          <DownloadIcon size={14} />
          Export citations
        </button>
        <span style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center" }}>
          APA · Bluebook · CGST style
        </span>
      </div>
    </aside>
  );
}

function SrcChip({ children, active }: { children: React.ReactNode; active?: boolean }) {
  return (
    <button
      type="button"
      className="v2-focus"
      style={{
        flex: "none",
        height: 24,
        padding: "0 10px",
        border: active ? 0 : "1px solid var(--border)",
        borderRadius: "var(--radius-pill)",
        background: active ? "var(--accent-soft)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        font: `500 11px/16px var(--font-sans-v2)`,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function SrcCard({ s }: { s: SourceCard }) {
  return (
    <div
      style={{
        padding: 14,
        borderRadius: "var(--radius-app-card)",
        border: s.active ? "2px solid var(--accent)" : "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        cursor: "pointer",
      }}
    >
      <TypeChip tone={s.typeTone}>{s.type}</TypeChip>
      <span style={{ fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>{s.title}</span>
      <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{s.citation}</span>
      {s.extract && (
        <div
          style={{
            marginTop: 4,
            paddingLeft: 10,
            borderLeft: "2px solid var(--border)",
            fontSize: 12,
            lineHeight: "18px",
            color: "var(--text-secondary)",
            maxHeight: s.active ? 66 : 40,
            overflow: "hidden",
            maskImage: s.active ? "linear-gradient(to bottom, black 60%, transparent 100%)" : undefined,
            WebkitMaskImage: s.active ? "linear-gradient(to bottom, black 60%, transparent 100%)" : undefined,
          }}
        >
          {s.extract}
        </div>
      )}
    </div>
  );
}
