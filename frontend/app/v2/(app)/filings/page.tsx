"use client";

import { Suspense, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  ClockIcon,
} from "@/components/v2/icons";
import { ErrorBanner } from "@/components/v2/ui/ErrorBanner";
import { EmptyState } from "@/components/v2/ui/EmptyState";
import { LoadingState } from "@/components/v2/ui/LoadingState";
import { Monogram } from "@/components/v2/ui/Monogram";
import {
  formatPeriod,
  formatRelative,
  formatRupees,
  initialsFrom,
  prettyReturnType,
  useFilingDetail,
  useFilingList,
  useFilingMutations,
  workflowStep,
  type AuditRow,
  type FilingListRow,
  type FilingPayload,
  type FilingRow,
  type ReadinessBlocker,
  type ReadinessSnapshot,
} from "./useFilingsData";

/* --------------------------------- Shared styles --------------------------------- */

const CARD: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-app-card)",
  boxShadow: "var(--shadow-card)",
};

const LABEL: CSSProperties = {
  fontSize: "var(--fs-label)",
  lineHeight: "var(--lh-label)",
  fontWeight: "var(--fw-medium)",
  letterSpacing: "var(--tr-label)",
  textTransform: "uppercase",
  color: "var(--text-muted)",
};

/* --------------------------------- Page shell --------------------------------- */

export default function FilingsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <FilingsRouter />
    </Suspense>
  );
}

function FilingsRouter() {
  const params = useSearchParams();
  const id = params.get("id");
  return id ? <DetailView filingId={id} /> : <PickerView />;
}


/* --------------------------------- PICKER --------------------------------- */

function PickerView() {
  const [statusFilter, setStatusFilter] = useState<"draft" | "approved" | "filed" | "all">("draft");
  const filter = statusFilter === "all" ? {} : { status: statusFilter };
  const { filings, loading, error, reload } = useFilingList(filter);

  return (
    <div style={{ padding: 32, display: "flex", flexDirection: "column", gap: 24, maxWidth: 1504, width: "100%" }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1 style={{
            margin: 0,
            fontSize: "var(--fs-display)",
            lineHeight: "var(--lh-display)",
            fontWeight: "var(--fw-semi)",
            letterSpacing: "var(--tr-display)",
            color: "var(--text-primary)",
          }}>
            Filings
          </h1>
          <p style={{ margin: 0, fontSize: "var(--fs-body)", lineHeight: "var(--lh-body)", color: "var(--text-secondary)" }}>
            Open a filing to review payload, resolve blockers, approve, and mark filed.
          </p>
        </div>
        <StatusToggle value={statusFilter} onChange={setStatusFilter} />
      </div>

      {error && <ErrorBanner message={`Could not load filings: ${error}`} onRetry={reload} />}

      <section style={{ ...CARD, overflow: "hidden" }}>
        <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
            {statusFilter === "all" ? "All filings" : `${statusFilter[0].toUpperCase()}${statusFilter.slice(1)}`}
          </h2>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {filings ? `${filings.length} shown` : loading ? "Loading…" : "No filings"}
          </span>
        </div>

        {loading && filings === null ? (
          <LoadingState message="Loading filings…" />
        ) : !filings || filings.length === 0 ? (
          <EmptyState message={error ? "Could not load filings." : "No filings match this filter."} />
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 320 }} />
              <col style={{ width: 200 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 180 }} />
            </colgroup>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <Th>Client</Th>
                <Th>GSTIN</Th>
                <Th>Return</Th>
                <Th>Period</Th>
                <Th>Status</Th>
                <Th>Last updated</Th>
              </tr>
            </thead>
            <tbody>
              {filings.map((f) => <PickerRow key={f.id} row={f} />)}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function PickerRow({ row }: { row: FilingListRow }) {
  return (
    <tr className="v2-row" style={{ height: 56, borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "0 24px" }}>
        <Link
          href={`/v2/filings?id=${row.id}`}
          className="v2-focus"
          style={{ display: "flex", alignItems: "center", gap: 12, color: "inherit", textDecoration: "none" }}
        >
          <Monogram initials={initialsFrom(row.client_name)} />
          <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>
            {row.client_name}
          </span>
        </Link>
      </td>
      <td className="mono" style={{ padding: "0 12px", color: "var(--text-secondary)" }}>{row.gstin}</td>
      <td style={{ padding: "0 12px", color: "var(--text-primary)" }}>{prettyReturnType(row.return_type)}</td>
      <td style={{ padding: "0 12px", color: "var(--text-primary)" }} className="tabular">{formatPeriod(row.period)}</td>
      <td style={{ padding: "0 12px" }}>
        <StatusChip status={row.status} />
      </td>
      <td style={{ padding: "0 12px", color: "var(--text-muted)", fontSize: 13 }}>{formatRelative(row.updated_at)}</td>
    </tr>
  );
}

function StatusChip({ status }: { status: FilingListRow["status"] }) {
  const cfg =
    status === "filed"
      ? { bg: "var(--success-soft)", fg: "var(--success)", label: "Filed" }
      : status === "approved"
      ? { bg: "var(--accent-soft)", fg: "var(--accent)", label: "Approved" }
      : { bg: "var(--warning-soft)", fg: "var(--warning)", label: "Draft" };
  return (
    <span style={{ padding: "3px 8px", borderRadius: "var(--radius-chip)", background: cfg.bg, color: cfg.fg, fontSize: 12, fontWeight: "var(--fw-medium)" }}>
      {cfg.label}
    </span>
  );
}

function StatusToggle({
  value, onChange,
}: {
  value: "draft" | "approved" | "filed" | "all";
  onChange: (v: "draft" | "approved" | "filed" | "all") => void;
}) {
  const opts: Array<{ v: typeof value; label: string }> = [
    { v: "draft", label: "Draft" },
    { v: "approved", label: "Approved" },
    { v: "filed", label: "Filed" },
    { v: "all", label: "All" },
  ];
  return (
    <div style={{ height: 32, display: "flex", border: "1px solid var(--border)", borderRadius: "var(--radius-input)", overflow: "hidden" }}>
      {opts.map((o, i) => {
        const active = value === o.v;
        return (
          <button
            key={o.v}
            type="button"
            onClick={() => onChange(o.v)}
            className="v2-focus-inset"
            style={{
              padding: "0 14px",
              border: 0,
              borderLeft: i === 0 ? "none" : "1px solid var(--border)",
              background: active ? "var(--accent-soft)" : "transparent",
              color: active ? "var(--accent)" : "var(--text-secondary)",
              font: `500 13px/20px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th style={{ padding: "10px 24px", textAlign: "left", ...LABEL }}>
      {children}
    </th>
  );
}

/* --------------------------------- DETAIL --------------------------------- */

function DetailView({ filingId }: { filingId: string }) {
  const { data, loading, error, reload } = useFilingDetail(filingId);
  const mut = useFilingMutations(filingId, reload);

  const filing = data.filing;
  const readiness = data.readiness;

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0, background: "var(--bg)" }}>
      {error && (
        <div style={{ padding: "12px 24px", background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
          <ErrorBanner message={`Could not load filing: ${error}`} onRetry={reload} />
        </div>
      )}
      {mut.error && (
        <div style={{ padding: "12px 24px", background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
          <ErrorBanner message={`Action failed: ${mut.error}`} />
        </div>
      )}
      <ReturnHeader filing={filing} readiness={readiness} mut={mut} loading={loading && !filing} />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <WorkflowRail filing={filing} readiness={readiness} loading={loading && !filing} />
        <Canvas filing={filing} readiness={readiness} loading={loading && !filing} />
        <ActivityRail items={data.activity} loading={loading && data.activity === null} />
      </div>
    </div>
  );
}

/* --------------------------------- Return header --------------------------------- */

function ReturnHeader({
  filing, readiness, mut, loading,
}: {
  filing: FilingRow | null;
  readiness: ReadinessSnapshot | null;
  mut: ReturnType<typeof useFilingMutations>;
  loading: boolean;
}) {
  const blockerCount = readiness?.blockers.length ?? 0;
  const returnLabel = filing ? `${prettyReturnType(filing.return_type)} — ${formatPeriod(filing.period)}` : "Filing";
  const clientName = filing?.payload?.gstin ? "" : "";  // Client name lookup requires join we don't have client-side; show GSTIN instead.
  const gstin = filing?.payload?.gstin ?? "";

  const canApprove = filing?.status === "draft" && blockerCount === 0 && !mut.running;
  const canFile = filing?.status === "approved" && !mut.running;

  return (
    <div style={{
      flex: "none",
      boxSizing: "border-box",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface)",
      padding: "16px 32px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
    }}>
      <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
        <Link href="/v2/filings" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Filings</Link>
        {" › "}
        {filing ? `${prettyReturnType(filing.return_type)} › ${formatPeriod(filing.period)}` : "Loading…"}
      </span>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <Monogram initials={initialsFrom(gstin || returnLabel)} />
          <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
            <h1 style={{
              margin: 0,
              fontSize: "var(--fs-h1)",
              lineHeight: "var(--lh-h1)",
              fontWeight: "var(--fw-semi)",
              letterSpacing: "var(--tr-h1)",
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
            }}>
              {loading ? "Loading filing…" : returnLabel}
            </h1>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
              {gstin ? <><span className="mono" style={{ fontSize: 12 }}>{gstin}</span></> : "—"}
              {filing && ` · Rule pack ${filing.rule_pack_version}`}
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flex: "none" }}>
          {blockerCount > 0 && (
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "4px 10px", borderRadius: "var(--radius-chip)",
              background: "var(--warning-soft)", color: "var(--warning)",
              fontSize: 12, lineHeight: "16px", fontWeight: "var(--fw-medium)",
            }}>
              <AlertTriangleIcon size={12} />
              {blockerCount} blocker{blockerCount === 1 ? "" : "s"}
            </span>
          )}
          {filing && <VDiv />}
          {filing && (
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "4px 10px", border: "1px solid var(--border)",
              borderRadius: "var(--radius-chip)", color: "var(--text-secondary)",
              fontSize: 12, lineHeight: "16px", fontWeight: "var(--fw-medium)",
            }}>
              <ClockIcon size={12} />
              Updated {formatRelative(filing.updated_at)}
            </span>
          )}
          {filing && <VDiv />}
          <button
            type="button"
            onClick={mut.approve}
            disabled={!canApprove}
            title={canApprove ? "Approve this filing" : blockerCount > 0 ? `Resolve ${blockerCount} blocker${blockerCount === 1 ? "" : "s"} first` : filing?.status === "approved" ? "Already approved" : filing?.status === "filed" ? "Already filed" : "Loading…"}
            style={{
              height: 32, padding: "0 12px",
              border: "1px solid var(--border)", borderRadius: "var(--radius-input)",
              background: "var(--surface)", color: canApprove ? "var(--text-primary)" : "var(--text-muted)",
              font: `500 13px/20px var(--font-sans-v2)`,
              cursor: canApprove ? "pointer" : "not-allowed",
              opacity: canApprove ? 1 : 0.6,
            }}
          >
            {mut.running && filing?.status === "draft" ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            onClick={() => mut.markFiled()}
            disabled={!canFile}
            title={canFile ? "Mark filed to GSTN" : filing?.status === "filed" ? "Already filed" : "Approve first"}
            style={{
              height: 32, padding: "0 14px",
              border: 0, borderRadius: "var(--radius-input)",
              background: "var(--accent)", color: "var(--on-accent)",
              font: `500 13px/20px var(--font-sans-v2)`,
              cursor: canFile ? "pointer" : "not-allowed",
              opacity: canFile ? 1 : 0.6,
            }}
          >
            {mut.running && filing?.status === "approved" ? "Filing…" : "File to GSTN"}
          </button>
        </div>
      </div>
    </div>
  );
}

function VDiv() {
  return <span style={{ width: 1, height: 24, background: "var(--border)" }} />;
}

/* --------------------------------- Workflow rail --------------------------------- */

const STEP_LABELS: Array<{ label: string; subtitle: string }> = [
  { label: "Data ingest", subtitle: "Purchase register + 2B" },
  { label: "Validation", subtitle: "Rules R001…R012 executed" },
  { label: "Reconciliation", subtitle: "Match against GSTR-2B" },
  { label: "Computation", subtitle: "Tax + ITC computed" },
  { label: "CA review", subtitle: "Verify + approve" },
  { label: "File to GSTN", subtitle: "Push, acknowledge, archive" },
];

function WorkflowRail({
  filing, readiness, loading,
}: {
  filing: FilingRow | null;
  readiness: ReadinessSnapshot | null;
  loading: boolean;
}) {
  const { activeIndex, percent } = workflowStep(filing, readiness);
  return (
    <aside style={{
      width: 260, flex: "none",
      background: "var(--surface)",
      borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ padding: "20px 20px 16px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={LABEL}>Filing workflow</span>
        <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }} className="tabular">
          {loading ? "Loading…" : `Step ${activeIndex + 1} of ${STEP_LABELS.length} · ${percent}% complete`}
        </span>
        <div style={{ height: 4, background: "var(--border)", borderRadius: "var(--radius-pill)", overflow: "hidden" }}>
          <div style={{ width: `${percent}%`, height: 4, background: "var(--accent)" }} />
        </div>
      </div>
      <div style={{ flex: 1, padding: "16px 0", display: "flex", flexDirection: "column" }}>
        {STEP_LABELS.map((step, i) => (
          <StepNode
            key={i}
            step={step}
            status={i < activeIndex ? "completed" : i === activeIndex ? "active" : "upcoming"}
            isLast={i === STEP_LABELS.length - 1}
          />
        ))}
      </div>
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {filing ? `Created ${new Date(filing.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}` : "—"}
        </span>
      </div>
    </aside>
  );
}

function StepNode({
  step, status, isLast,
}: {
  step: { label: string; subtitle: string };
  status: "completed" | "active" | "upcoming";
  isLast: boolean;
}) {
  const active = status === "active";
  const completed = status === "completed";
  const railColor = completed ? "var(--success)" : "var(--border)";

  return (
    <div style={{
      position: "relative",
      padding: active ? "12px 20px" : "10px 20px",
      background: active ? "var(--row-hover-accent)" : "transparent",
      display: "flex", gap: 12,
    }}>
      {active && (
        <span style={{ position: "absolute", left: 0, top: 8, bottom: 8, width: 3, borderRadius: "0 3px 3px 0", background: "var(--accent)" }} />
      )}
      <div style={{ flex: "none", display: "flex", flexDirection: "column", alignItems: "center", width: 24 }}>
        <NodeCircle status={status} />
        {!isLast && (
          <span style={{ flex: 1, width: 2, minHeight: 20, background: railColor, marginTop: 2, marginBottom: 2 }} />
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: isLast ? 0 : 8 }}>
        <span style={{
          display: "block",
          fontSize: 13, lineHeight: "18px", fontWeight: "var(--fw-medium)",
          color: active ? "var(--accent)" : completed ? "var(--text-primary)" : "var(--text-secondary)",
        }}>
          {step.label}
        </span>
        <span style={{ display: "block", marginTop: 2, fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>
          {step.subtitle}
        </span>
      </div>
    </div>
  );
}

function NodeCircle({ status }: { status: "completed" | "active" | "upcoming" }) {
  if (status === "completed") {
    return (
      <span style={{ width: 24, height: 24, flex: "none", borderRadius: "var(--radius-pill)", background: "var(--success-soft)", color: "var(--success)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <CheckCircleIcon size={14} />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span style={{ width: 24, height: 24, flex: "none", borderRadius: "var(--radius-pill)", background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ width: 8, height: 8, borderRadius: "var(--radius-pill)", background: "#fff" }} />
      </span>
    );
  }
  return (
    <span style={{ width: 24, height: 24, flex: "none", borderRadius: "var(--radius-pill)", background: "var(--surface)", border: "2px solid var(--border-strong)" }} />
  );
}

/* --------------------------------- Canvas --------------------------------- */

function Canvas({
  filing, readiness, loading,
}: {
  filing: FilingRow | null;
  readiness: ReadinessSnapshot | null;
  loading: boolean;
}) {
  return (
    <main style={{ flex: 1, minWidth: 0, padding: 24, display: "flex", flexDirection: "column", gap: 20, overflow: "auto" }}>
      {loading ? (
        <LoadingState message="Loading filing payload…" />
      ) : !filing ? (
        <EmptyState message="Filing not found." />
      ) : (
        <>
          <p style={{ margin: 0, fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)" }}>
            Verify the blocks below match your ledgers. Blockers must be resolved before filing.
          </p>
          <HeadlineCards payload={filing.payload} />
          {readiness && readiness.blockers.length > 0 && (
            <BlockersCard blockers={readiness.blockers} />
          )}
          {filing.return_type === "GSTR3B" && (
            <>
              <OutwardSuppliesTable payload={filing.payload} />
              <ItcTable payload={filing.payload} />
            </>
          )}
          {filing.return_type === "GSTR1" && <Gstr1Notice />}
        </>
      )}
    </main>
  );
}

function Gstr1Notice() {
  return (
    <section style={{ ...CARD, padding: 24, color: "var(--text-secondary)", fontSize: 13 }}>
      GSTR-1 detailed section rendering coming next. Payload data is available in the raw record.
    </section>
  );
}

/* --------------------------------- Headline cards --------------------------------- */

function HeadlineCards({ payload }: { payload: FilingPayload | null }) {
  const outward = payload?.sup_details?.osup_det;
  const itcNet = payload?.itc_elg?.itc_net;
  const cash = payload?.tx_pmt?.tx_pd_cash;

  const outwardTax = sumMoney(outward);
  const itcTotal = sumMoney(itcNet);
  const cashTotal = sumMoney(cash);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
      <HeadlineCard
        rail="var(--accent)"
        label="Outward tax (3.1a)"
        amount={formatRupees(outwardTax)}
        amountColor="var(--text-primary)"
        subs={[
          `Taxable value: ${formatRupees(outward?.txval)}`,
          `CGST: ${formatRupees(outward?.camt)}`,
          `SGST: ${formatRupees(outward?.samt)}`,
          `IGST: ${formatRupees(outward?.iamt)}`,
        ]}
      />
      <HeadlineCard
        rail="var(--success)"
        label="ITC available (4A)"
        amount={formatRupees(itcTotal)}
        amountColor="var(--success)"
        subs={[
          `CGST: ${formatRupees(itcNet?.camt)}`,
          `SGST: ${formatRupees(itcNet?.samt)}`,
          `IGST: ${formatRupees(itcNet?.iamt)}`,
          `Reversal (4B): ${formatRupees(0)}`,
        ]}
      />
      <HeadlineCard
        rail="var(--warning)"
        label="Net payable in cash"
        amount={formatRupees(cashTotal)}
        amountColor="var(--text-primary)"
        subs={[
          `CGST cash: ${formatRupees(cash?.camt)}`,
          `SGST cash: ${formatRupees(cash?.samt)}`,
          `IGST cash: ${formatRupees(cash?.iamt)}`,
          "Interest u/s 50: —",
        ]}
      />
    </div>
  );
}

function sumMoney(m: { camt?: number; samt?: number; iamt?: number; csamt?: number } | undefined | null): number {
  if (!m) return 0;
  return (m.camt ?? 0) + (m.samt ?? 0) + (m.iamt ?? 0) + (m.csamt ?? 0);
}

function HeadlineCard({
  rail, label, amount, amountColor, subs,
}: {
  rail: string; label: string; amount: string; amountColor: string; subs: React.ReactNode[];
}) {
  return (
    <div style={{
      ...CARD,
      minHeight: 148,
      padding: "16px 16px 16px 20px",
      display: "flex", flexDirection: "column", gap: 6,
      borderLeft: `3px solid ${rail}`,
    }}>
      <span style={LABEL}>{label}</span>
      <span className="tabular" style={{
        fontSize: "var(--fs-money-lg)",
        lineHeight: "var(--lh-money-lg)",
        fontWeight: "var(--fw-semi)",
        color: amountColor,
      }}>
        {amount}
      </span>
      <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 4 }}>
        {subs.map((s, i) => (
          <span key={i} className="tabular" style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }}>
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------- Blockers --------------------------------- */

function BlockersCard({ blockers }: { blockers: ReadinessBlocker[] }) {
  return (
    <div style={{
      borderRadius: "var(--radius-app-card)",
      border: "1px solid var(--danger)",
      borderLeft: "3px solid var(--danger)",
      background: "var(--danger-zone-bg)",
      padding: "16px 20px",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <AlertTriangleIcon size={18} style={{ color: "var(--danger)" }} />
        <h2 style={{ margin: 0, fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--danger)" }}>
          {blockers.length} blocker{blockers.length === 1 ? "" : "s"} before you can file
        </h2>
        <span style={{
          padding: "2px 8px", borderRadius: "var(--radius-pill)",
          background: "var(--surface)", border: "1px solid var(--danger)",
          color: "var(--danger)", fontSize: 11, fontWeight: "var(--fw-semi)",
        }}>
          {blockers.length} open
        </span>
      </div>
      {blockers.map((b, i) => <BlockerRow key={i} blocker={b} />)}
    </div>
  );
}

function BlockerRow({ blocker }: { blocker: ReadinessBlocker }) {
  const severity = blocker.severity ?? "error";
  const badgeFg = severity === "warning" ? "var(--warning)" : "var(--danger)";
  const badgeBg = severity === "warning" ? "var(--warning-soft)" : "var(--danger-soft)";
  const badgeText = severity === "warning" ? "W" : "E";
  const text = blocker.message ?? `${blocker.code} (${blocker.owner})`;
  return (
    <div style={{
      minHeight: 48, padding: "10px 12px",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: "var(--radius-chip)",
      display: "flex", alignItems: "center", gap: 12,
    }}>
      <span style={{
        flex: "none", height: 20, padding: "0 6px",
        display: "flex", alignItems: "center",
        borderRadius: 4, background: badgeBg, color: badgeFg,
        fontSize: 11, fontWeight: "var(--fw-semi)",
      }}>
        {badgeText}
      </span>
      <span style={{ flex: "none", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono-v2)" }}>
        {blocker.code}
      </span>
      <span style={{ flex: 1, minWidth: 0, fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>
        {text}
      </span>
      <span style={{ flex: "none", fontSize: 11, color: "var(--text-muted)", textTransform: "capitalize" }}>
        Owner: {blocker.owner}
      </span>
    </div>
  );
}

/* --------------------------------- Tables --------------------------------- */

function OutwardSuppliesTable({ payload }: { payload: FilingPayload | null }) {
  const s = payload?.sup_details;
  const rows = [
    { label: "(a) Outward taxable supplies (other than zero-rated)", m: s?.osup_det },
    { label: "(b) Outward taxable supplies (zero-rated)", m: s?.osup_zero, hasCG: false },
    { label: "(c) Other outward supplies (nil-rated, exempt)", txvalOnly: s?.osup_nil_exmp?.txval },
    { label: "(d) Inward supplies liable to reverse charge", m: s?.isup_rev },
    { label: "(e) Non-GST outward supplies", txvalOnly: s?.osup_nongst?.txval },
  ];
  const totalTx = rows.reduce((sum, r) => sum + (r.m?.txval ?? r.txvalOnly ?? 0), 0);
  const totalC = rows.reduce((sum, r) => sum + (r.m?.camt ?? 0), 0);
  const totalS = rows.reduce((sum, r) => sum + (r.m?.samt ?? 0), 0);
  const totalI = rows.reduce((sum, r) => sum + (r.m?.iamt ?? 0), 0);
  const totalCs = rows.reduce((sum, r) => sum + (r.m?.csamt ?? 0), 0);

  return (
    <SectionCard title="Outward supplies (3.1)">
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <ThLeft>Nature</ThLeft>
            <ThRight>Taxable value</ThRight>
            <ThRight>CGST</ThRight>
            <ThRight>SGST</ThRight>
            <ThRight>IGST</ThRight>
            <ThRight>Cess</ThRight>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
              <Td>{r.label}</Td>
              <TdRight>{formatRupees(r.m?.txval ?? r.txvalOnly ?? 0)}</TdRight>
              <TdRight>{formatRupees(r.m?.camt ?? 0)}</TdRight>
              <TdRight>{formatRupees(r.m?.samt ?? 0)}</TdRight>
              <TdRight>{formatRupees(r.m?.iamt ?? 0)}</TdRight>
              <TdRight>{formatRupees(r.m?.csamt ?? 0)}</TdRight>
            </tr>
          ))}
          <tr style={{ background: "var(--group-header)" }}>
            <Td bold>Total</Td>
            <TdRight bold>{formatRupees(totalTx)}</TdRight>
            <TdRight bold>{formatRupees(totalC)}</TdRight>
            <TdRight bold>{formatRupees(totalS)}</TdRight>
            <TdRight bold>{formatRupees(totalI)}</TdRight>
            <TdRight bold>{formatRupees(totalCs)}</TdRight>
          </tr>
        </tbody>
      </table>
    </SectionCard>
  );
}

function ItcTable({ payload }: { payload: FilingPayload | null }) {
  const avl = payload?.itc_elg?.itc_avl ?? [];
  const net = payload?.itc_elg?.itc_net;

  const displayRows: Array<{ label: string; m: { camt?: number; samt?: number; iamt?: number; csamt?: number } | undefined; highlight?: boolean }> = [
    { label: "(1) Import of goods", m: findByTy(avl, "IMPG") },
    { label: "(2) Import of services", m: findByTy(avl, "IMPS") },
    { label: "(3) Inward supplies liable to reverse charge", m: findByTy(avl, "ISRC") },
    { label: "(4) Inward supplies from ISD", m: findByTy(avl, "ISD") },
    { label: "(5) All other ITC", m: findByTy(avl, "OTH"), highlight: true },
  ];

  return (
    <SectionCard title="ITC available (4A)">
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <ThLeft>Head</ThLeft>
            <ThRight>IGST</ThRight>
            <ThRight>CGST</ThRight>
            <ThRight>SGST</ThRight>
            <ThRight>Cess</ThRight>
          </tr>
        </thead>
        <tbody>
          {displayRows.map((r, i) => {
            const color = r.highlight ? "var(--success)" : undefined;
            return (
              <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                <Td>{r.label}</Td>
                <TdRight color={color}>{formatRupees(r.m?.iamt ?? 0)}</TdRight>
                <TdRight color={color}>{formatRupees(r.m?.camt ?? 0)}</TdRight>
                <TdRight color={color}>{formatRupees(r.m?.samt ?? 0)}</TdRight>
                <TdRight>{formatRupees(r.m?.csamt ?? 0)}</TdRight>
              </tr>
            );
          })}
          <tr style={{ background: "var(--group-header)" }}>
            <Td bold>Total</Td>
            <TdRight bold color="var(--success)">{formatRupees(net?.iamt ?? 0)}</TdRight>
            <TdRight bold color="var(--success)">{formatRupees(net?.camt ?? 0)}</TdRight>
            <TdRight bold color="var(--success)">{formatRupees(net?.samt ?? 0)}</TdRight>
            <TdRight bold>{formatRupees(net?.csamt ?? 0)}</TdRight>
          </tr>
        </tbody>
      </table>
    </SectionCard>
  );
}

function findByTy(avl: Array<{ ty: string; camt?: number; samt?: number; iamt?: number; csamt?: number }>, ty: string) {
  return avl.find((r) => r.ty === ty);
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ ...CARD, overflow: "hidden" }}>
      <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--border)" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fs-h2)", lineHeight: "var(--lh-h2)", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>
          {title}
        </h3>
      </div>
      {children}
    </section>
  );
}

function ThLeft({ children }: { children: React.ReactNode }) {
  return <th style={{ padding: "10px 20px", textAlign: "left", ...LABEL }}>{children}</th>;
}
function ThRight({ children }: { children: React.ReactNode }) {
  return <th style={{ padding: "10px 20px", textAlign: "right", ...LABEL }}>{children}</th>;
}
function Td({ children, bold }: { children: React.ReactNode; bold?: boolean }) {
  return (
    <td style={{ padding: "10px 20px", fontSize: 13, lineHeight: "18px", color: "var(--text-primary)", fontWeight: bold ? "var(--fw-semi)" : "var(--fw-regular)" }}>
      {children}
    </td>
  );
}
function TdRight({ children, bold, color }: { children: React.ReactNode; bold?: boolean; color?: string }) {
  return (
    <td className="tabular" style={{ padding: "10px 20px", textAlign: "right", fontSize: 13, lineHeight: "18px", color: color ?? "var(--text-primary)", fontWeight: bold ? "var(--fw-semi)" : "var(--fw-regular)" }}>
      {children}
    </td>
  );
}

/* --------------------------------- Activity rail --------------------------------- */

function ActivityRail({ items, loading }: { items: AuditRow[] | null; loading: boolean }) {
  return (
    <aside style={{
      width: 340, flex: "none",
      background: "var(--surface)",
      borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ height: 56, padding: "0 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0, fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Activity</h2>
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: "20px" }}>
        {loading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading activity…</div>
        ) : !items || items.length === 0 ? (
          <EmptyState variant="inline" message="No audit events for this filing yet." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16, borderLeft: "1px solid var(--border)", paddingLeft: 20, marginLeft: 4 }}>
            {items.map((it) => <ActivityRow key={it.id} row={it} />)}
          </div>
        )}
      </div>
    </aside>
  );
}

function ActivityRow({ row }: { row: AuditRow }) {
  const tone = toneForAction(row.action);
  const dotColor =
    tone === "success" ? "var(--success)" :
    tone === "warning" ? "var(--warning)" :
    tone === "danger" ? "var(--danger)" :
    tone === "accent" ? "var(--accent)" : "var(--border-strong)";
  return (
    <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{
        position: "absolute", left: -25, top: 4, width: 9, height: 9,
        borderRadius: "var(--radius-pill)",
        background: dotColor, boxShadow: "0 0 0 3px var(--surface)",
      }} />
      <span style={{ fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>
        <strong style={{ fontWeight: 500 }}>{humanize(row.action)}</strong>
        {row.user_email && ` by ${row.user_email}`}
      </span>
      <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>
        {formatRelative(row.at)}
      </span>
    </div>
  );
}

function toneForAction(action: string): "success" | "warning" | "danger" | "accent" | "neutral" {
  if (action.startsWith("filing.filed") || action.startsWith("filing.marked_filed") || action.startsWith("match.confirmed") || action.startsWith("flag.resolved")) return "success";
  if (action.startsWith("filing.approved")) return "accent";
  if (action.startsWith("flag.raised") || action.startsWith("filing.rejected") || action.startsWith("filing.overdue")) return "danger";
  return "neutral";
}

function humanize(action: string): string {
  const parts = action.replace(".", " ").replace(/_/g, " ").split(" ");
  if (parts.length === 0) return action;
  return parts[0][0].toUpperCase() + parts[0].slice(1) + (parts.length > 1 ? " " + parts.slice(1).join(" ") : "");
}

/* --------------------------------- Error banner --------------------------------- */

