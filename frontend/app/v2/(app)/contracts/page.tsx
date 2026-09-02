"use client";

import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import {
  AlertTriangleIcon,
  ArrowUpRightIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  FileTextIcon,
  MessageSquareIcon,
  MoreHorizontalIcon,
  SearchIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { LoadingState } from "@/components/v2/ui/LoadingState";
import {
  useContractsData,
  useOcrDetail,
  severityCounts,
  severityFor,
  statusCounts,
  filterRows,
  formatBytes,
  formatDate,
  formatConfidence,
  formatPaise,
  prettyDirection,
  prettyStatus,
  type OcrListRow,
  type OcrDetail,
  type Sev,
} from "./useContractsData";

/* Design/backend gap: the Figma port shows a legal-contract review UI
 * (severity-ranked clauses, statutory refs, "why this matters"). The backend
 * ships an OCR pipeline for GST invoices (9 extracted fields with per-field
 * confidence). We wire the panel to real OCR extractions here — each
 * extraction is treated as a "document" and its fields as "issues" to
 * review. The document viewer on the left stays decorative until a PDF
 * renderer with real coordinates ships. */

const sevFg: Record<Sev, string> = { high: "var(--danger)", medium: "var(--warning)", low: "var(--success)" };
const sevBg: Record<Sev, string> = { high: "var(--danger-soft)", medium: "var(--warning-soft)", low: "var(--success-soft)" };
const sevLabel: Record<Sev, string> = { high: "Low conf", medium: "Verify", low: "Trusted" };

const LABEL: CSSProperties = {
  fontSize: 11,
  lineHeight: "16px",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

export default function ContractsPage() {
  const { rows, firm, loading, error, reload } = useContractsData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState<string>("");

  const filtered = useMemo(() => filterRows(rows, query), [rows, query]);
  const sevCounts = useMemo(() => severityCounts(rows), [rows]);
  const stCounts = useMemo(() => statusCounts(rows), [rows]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0, background: "var(--bg)" }}>
      <DocHeader
        firmName={firm?.name ?? null}
        totalCount={rows?.length ?? 0}
        sevCounts={sevCounts}
        latestUpload={rows && rows.length > 0 ? rows[0] : null}
      />
      <ScopeNotice />
      {error && (
        <div style={{ flex: "none", padding: "8px 32px" }}>
          <ErrorBanner message={`Failed to load extractions — ${error}`} onRetry={reload} />
        </div>
      )}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <DocViewer selectedFilename={selectedId ? filtered.find((r) => r.id === selectedId)?.source_filename ?? null : null} />
        <AnalysisPanel
          rows={filtered}
          totalCount={rows?.length ?? 0}
          statusBreakdown={stCounts}
          selectedId={selectedId}
          onSelect={(id) => setSelectedId(id)}
          query={query}
          onQuery={setQuery}
          loading={loading}
        />
      </div>
    </div>
  );
}

/* --------------------------------- Scope notice --------------------------------- */

function ScopeNotice() {
  return (
    <div
      style={{
        flex: "none",
        padding: "10px 32px",
        borderBottom: "1px solid var(--border)",
        background: "var(--accent-soft)",
        color: "var(--text-primary)",
        fontSize: 12,
        lineHeight: "18px",
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
      }}
    >
      <span style={{ color: "var(--accent)", marginTop: 1 }}>
        <AlertTriangleIcon size={14} />
      </span>
      <span>
        <strong style={{ fontWeight: "var(--fw-semi)" }}>Contract-clause analysis ships in a future release.</strong>{" "}
        Today this pane displays OCR extractions this firm has captured from GST invoices. Each row is one uploaded
        document; the analysis panel on the right lists per-field extraction results and confidence scores.
      </span>
    </div>
  );
}

/* --------------------------------- Header --------------------------------- */

function DocHeader({
  firmName,
  totalCount,
  sevCounts,
  latestUpload,
}: {
  firmName: string | null;
  totalCount: number;
  sevCounts: { high: number; medium: number; low: number; total: number };
  latestUpload: OcrListRow | null;
}) {
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
        Documents › OCR extractions › {firmName ?? "This firm"}
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
            OCR extractions — {firmName ?? "…"}
          </h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flex: "none" }}>
          <SevPill sev="high" count={sevCounts.high} />
          <SevPill sev="medium" count={sevCounts.medium} />
          <SevPill sev="low" count={sevCounts.low} />
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
              opacity: 0.5,
            }}
            disabled
            title="Share with client — coming with contracts backend"
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
        <MetaChip>{totalCount} extractions</MetaChip>
        {latestUpload && <MetaChip>Latest: {latestUpload.source_filename}</MetaChip>}
        {latestUpload && <MetaChip>{formatBytes(latestUpload.source_bytes_size)}</MetaChip>}
        {latestUpload && <MetaChip>Uploaded {formatDate(latestUpload.created_at)}</MetaChip>}
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
        cursor: "not-allowed",
        opacity: 0.5,
      }}
      disabled
      title="Export report — coming with contracts backend"
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
        maxWidth: 300,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
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

/* The viewer is a static Figma port. Rendering the real source PDF requires
 * a per-page image + clause-coordinate map, both of which land with the
 * contracts backend. Keeping it visible for design continuity. */

function DocViewer({ selectedFilename }: { selectedFilename: string | null }) {
  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--bg)", borderRight: "1px solid var(--border)" }}>
      <div style={{ flex: 1, overflow: "auto", padding: 48, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12 }}>
        <FileTextIcon size={32} style={{ color: "var(--text-muted)" }} />
        <span style={{ fontSize: 14, fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>
          PDF preview not yet wired
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)", textAlign: "center", maxWidth: 420 }}>
          {selectedFilename
            ? <>Selected: <span className="mono" style={{ color: "var(--text-primary)" }}>{selectedFilename}</span>. See the panel on the right for extracted fields.</>
            : "Select an extraction on the right to see the source filename here."}
        </span>
        <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
          Live PDF rendering with clause coordinates ships with the contracts backend.
        </span>
      </div>
    </div>
  );
}

function IconBtn({ children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const disabled = rest.disabled;
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
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

/* --------------------------------- Paper page (decorative) --------------------------------- */

/* --------------------------------- Analysis panel --------------------------------- */

function AnalysisPanel({
  rows,
  totalCount,
  statusBreakdown,
  selectedId,
  onSelect,
  query,
  onQuery,
  loading,
}: {
  rows: OcrListRow[];
  totalCount: number;
  statusBreakdown: { draft: number; accepted: number; rejected: number };
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  query: string;
  onQuery: (q: string) => void;
  loading: boolean;
}) {
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
      <TabRow extractionCount={totalCount} />
      <SubFilterRow rows={rows} totalCount={totalCount} statusBreakdown={statusBreakdown} query={query} onQuery={onQuery} />
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {loading && rows.length === 0 && <LoadingState message="Loading extractions…" />}
        {!loading && rows.length === 0 && (
          totalCount === 0
            ? <EmptyState message="No OCR extractions yet." hint="Upload an invoice through the OCR pipeline to see it here." />
            : <EmptyState message="No extractions match this filter." />
        )}
        {rows.map((row) => (
          row.id === selectedId ? (
            <IssueExpanded key={row.id} row={row} onCollapse={() => onSelect(null)} />
          ) : (
            <IssueCollapsed key={row.id} row={row} onExpand={() => onSelect(row.id)} />
          )
        ))}
      </div>
    </aside>
  );
}

function TabRow({ extractionCount }: { extractionCount: number }) {
  const tabs = [
    { label: `Extractions (${extractionCount})`, active: true, enabled: true },
    { label: "Summary", enabled: false },
    { label: "Key terms", enabled: false },
    { label: "Compliance", enabled: false },
  ];
  return (
    <div style={{ height: 48, flex: "none", borderBottom: "1px solid var(--border)", padding: "0 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div style={{ display: "flex", alignItems: "stretch", height: "100%" }}>
        {tabs.map((t) => (
          <button
            key={t.label}
            type="button"
            className="v2-focus-inset"
            disabled={!t.enabled}
            title={t.enabled ? undefined : "Coming with contracts backend"}
            style={{
              padding: "0 14px",
              border: 0,
              background: "transparent",
              color: t.active ? "var(--text-primary)" : "var(--text-muted)",
              font: `${t.active ? 600 : 400} 13px/20px var(--font-sans-v2)`,
              cursor: t.enabled ? "pointer" : "not-allowed",
              boxShadow: t.active ? "inset 0 -2px 0 var(--accent)" : undefined,
              opacity: t.enabled ? 1 : 0.5,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="v2-btn-secondary v2-focus"
        disabled
        title="Sort — coming soon"
        style={{
          height: 28,
          padding: "0 10px",
          display: "flex",
          alignItems: "center",
          gap: 6,
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-input)",
          background: "var(--surface)",
          color: "var(--text-muted)",
          font: `500 12px/16px var(--font-sans-v2)`,
          cursor: "not-allowed",
          opacity: 0.6,
        }}
      >
        Newest first
        <ChevronDownIcon size={12} />
      </button>
    </div>
  );
}

function SubFilterRow({
  rows,
  totalCount,
  statusBreakdown,
  query,
  onQuery,
}: {
  rows: OcrListRow[];
  totalCount: number;
  statusBreakdown: { draft: number; accepted: number; rejected: number };
  query: string;
  onQuery: (q: string) => void;
}) {
  const showing = rows.length;
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
          placeholder="Filter by filename or adapter…"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          style={{
            flex: 1, minWidth: 0, border: 0, outline: 0, background: "transparent",
            font: `400 12px/16px var(--font-sans-v2)`, color: "var(--text-primary)",
          }}
        />
      </div>
      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
        {showing === totalCount
          ? `${totalCount} extractions · ${statusBreakdown.draft} draft · ${statusBreakdown.accepted} accepted · ${statusBreakdown.rejected} rejected`
          : `${showing} of ${totalCount} extractions`}
      </span>
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

function ConfidenceBadge({ pct, active }: { pct: number; active?: boolean }) {
  return (
    <span
      className="tabular"
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
      {pct}%
    </span>
  );
}

function StatusChip({ status }: { status: OcrListRow["status"] }) {
  const map: Record<OcrListRow["status"], { fg: string; bg: string }> = {
    draft: { fg: "var(--text-secondary)", bg: "var(--row-hover)" },
    accepted: { fg: "var(--success)", bg: "var(--success-soft)" },
    rejected: { fg: "var(--danger)", bg: "var(--danger-soft)" },
  };
  const { fg, bg } = map[status];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: "var(--radius-chip)",
        border: "1px solid var(--border)",
        background: bg,
        color: fg,
        fontSize: 11,
        fontWeight: "var(--fw-medium)",
      }}
    >
      {prettyStatus(status)}
    </span>
  );
}

function IssueCollapsed({ row, onExpand }: { row: OcrListRow; onExpand: () => void }) {
  const sev = severityFor(row.overall_confidence);
  const pct = Math.round(row.overall_confidence * 100);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onExpand}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onExpand(); } }}
      className="v2-focus"
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
        <SeverityChip sev={sev} />
        <ConfidenceBadge pct={pct} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 14, lineHeight: "20px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {row.source_filename}
        </span>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{row.adapter}</span>
        <ChevronDownIcon size={14} style={{ color: "var(--text-muted)" }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 4 }}>
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
          {prettyDirection(row.direction)}
        </span>
        <StatusChip status={row.status} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {formatBytes(row.source_bytes_size)} · uploaded {formatDate(row.created_at)}
        </span>
      </div>
    </div>
  );
}

function IssueExpanded({ row, onCollapse }: { row: OcrListRow; onCollapse: () => void }) {
  const { detail, loading, error } = useOcrDetail(row.id);
  const sev = severityFor(row.overall_confidence);
  const pct = Math.round(row.overall_confidence * 100);
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
        <div
          role="button"
          tabIndex={0}
          onClick={onCollapse}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCollapse(); } }}
          className="v2-focus"
          style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
        >
          <SeverityChip sev={sev} />
          <ConfidenceBadge pct={pct} active />
          <span style={{ flex: 1, minWidth: 0, fontSize: 14, lineHeight: "20px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {row.source_filename}
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{row.adapter}</span>
        </div>
        <div style={{ height: 1, background: "var(--border)" }} />

        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Extraction meta</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: 13, color: "var(--text-secondary)" }}>
            <span><strong style={{ color: "var(--text-primary)" }}>Direction:</strong> {prettyDirection(row.direction)}</span>
            <span><strong style={{ color: "var(--text-primary)" }}>Status:</strong> {prettyStatus(row.status)}</span>
            <span><strong style={{ color: "var(--text-primary)" }}>Size:</strong> {formatBytes(row.source_bytes_size)}</span>
            <span><strong style={{ color: "var(--text-primary)" }}>Uploaded:</strong> {formatDate(row.created_at)}</span>
            {detail && <span><strong style={{ color: "var(--text-primary)" }}>Adapter:</strong> {detail.adapter} v{detail.adapter_version}</span>}
          </div>
        </section>

        <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Extracted fields</span>
          {loading && <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)" }}>Loading fields…</p>}
          {error && <p style={{ margin: 0, fontSize: 13, color: "var(--danger)" }}>Failed to load fields — {error}</p>}
          {detail && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <FieldRow label="Supplier GSTIN" field={detail.supplier_gstin} threshold={detail.low_confidence_threshold} mono />
              <FieldRow label="Invoice number" field={detail.invoice_number} threshold={detail.low_confidence_threshold} mono />
              <FieldRow label="Invoice date" field={detail.invoice_date} threshold={detail.low_confidence_threshold} />
              <FieldRow label="HSN / SAC" field={detail.hsn_sac} threshold={detail.low_confidence_threshold} mono />
              <FieldRow label="Taxable value" field={detail.taxable_value_paise} threshold={detail.low_confidence_threshold} money />
              <FieldRow label="CGST" field={detail.cgst_paise} threshold={detail.low_confidence_threshold} money />
              <FieldRow label="SGST" field={detail.sgst_paise} threshold={detail.low_confidence_threshold} money />
              <FieldRow label="IGST" field={detail.igst_paise} threshold={detail.low_confidence_threshold} money />
              <FieldRow label="Total" field={detail.total_paise} threshold={detail.low_confidence_threshold} money />
            </div>
          )}
        </section>

        {detail && detail.warnings.length > 0 && (
          <section style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={LABEL}>Warnings ({detail.warnings.length})</span>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: "20px", color: "var(--text-primary)" }}>
              {detail.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </section>
        )}
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
          <IconBtn aria-label="Mark reviewed" disabled title="Accept/reject — use the OCR panel"><CheckCircleIcon size={16} /></IconBtn>
          <IconBtn aria-label="Comment" disabled title="Comments — coming soon"><MessageSquareIcon size={16} /></IconBtn>
          <IconBtn aria-label="More" disabled><MoreHorizontalIcon size={16} /></IconBtn>
        </div>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--text-muted)" }}>
          Accept / reject via OCR panel
          <ArrowUpRightIcon size={14} />
        </span>
      </div>
    </div>
  );
}

function FieldRow({
  label,
  field,
  threshold,
  mono,
  money,
}: {
  label: string;
  field: { value: string | null; confidence: number };
  threshold: number;
  mono?: boolean;
  money?: boolean;
}) {
  const low = field.confidence < threshold;
  const display =
    field.value == null
      ? "—"
      : money
      ? formatPaise(field.value)
      : field.value;
  return (
    <div
      style={{
        padding: "8px 10px",
        border: `1px solid ${low ? "var(--danger)" : "var(--border)"}`,
        background: low ? "var(--danger-soft)" : "var(--surface)",
        borderRadius: "var(--radius-chip)",
        display: "flex",
        flexDirection: "column",
        gap: 2,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "var(--tr-label)" }}>{label}</span>
        <span className="tabular" style={{ fontSize: 11, color: low ? "var(--danger)" : "var(--text-muted)", fontWeight: "var(--fw-medium)" }}>
          {formatConfidence(field.confidence)}
        </span>
      </div>
      <span
        className={mono ? "mono" : "tabular"}
        style={{ fontSize: 13, color: field.value == null ? "var(--text-muted)" : "var(--text-primary)", fontWeight: "var(--fw-medium)" }}
      >
        {display}
      </span>
    </div>
  );
}
