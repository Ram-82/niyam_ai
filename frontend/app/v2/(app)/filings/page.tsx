import type { CSSProperties } from "react";
import {
  AlertTriangleIcon,
  ArrowUpIcon,
  CheckCircleIcon,
  ClockIcon,
} from "@/components/v2/icons";
import { Monogram } from "@/components/v2/ui/Monogram";

type StepStatus = "completed" | "active" | "upcoming";
type Step = { label: string; status: StepStatus; subtitle: string };

const STEPS: Step[] = [
  { label: "Data ingest", status: "completed", subtitle: "Purchase register + 2B pulled · 21 inv + 15 2B rows" },
  { label: "Validation", status: "completed", subtitle: "9 flags — 5 errors, 4 warnings · resolved 12 Aug" },
  { label: "Reconciliation", status: "completed", subtitle: "10 matched · 2 probable · 6 supplier default · 3 missing" },
  { label: "Computation", status: "completed", subtitle: "Tax + ITC computed at rule pack v1.0.0" },
  { label: "CA review", status: "active", subtitle: "Verify + approve before submission" },
  { label: "File to GSTN", status: "upcoming", subtitle: "Push, acknowledge, archive" },
];

type SupplyRow = { label: string; taxable: string; cgst: string; sgst: string; igst: string; cess: string; total?: boolean };
const OUTWARD: SupplyRow[] = [
  { label: "(a) Outward taxable supplies (other than zero-rated)", taxable: "₹2,37,15,450", cgst: "₹19,17,236", sgst: "₹19,17,236", igst: "₹4,34,308", cess: "₹0" },
  { label: "(b) Outward taxable supplies (zero-rated)", taxable: "₹18,42,000", cgst: "₹0", sgst: "₹0", igst: "₹0", cess: "₹0" },
  { label: "(c) Other outward supplies (nil-rated, exempt)", taxable: "₹4,28,700", cgst: "₹0", sgst: "₹0", igst: "₹0", cess: "₹0" },
  { label: "(d) Inward supplies liable to reverse charge", taxable: "₹92,500", cgst: "₹8,325", sgst: "₹8,325", igst: "₹0", cess: "₹0" },
  { label: "(e) Non-GST outward supplies", taxable: "₹0", cgst: "₹0", sgst: "₹0", igst: "₹0", cess: "₹0" },
  { label: "Total", taxable: "₹2,60,78,650", cgst: "₹19,25,561", sgst: "₹19,25,561", igst: "₹4,34,308", cess: "₹0", total: true },
];

type ItcRow = { label: string; igst: string; cgst: string; sgst: string; cess: string; total?: boolean; highlight?: boolean };
const ITC: ItcRow[] = [
  { label: "(1) Import of goods", igst: "₹0", cgst: "₹0", sgst: "₹0", cess: "₹0" },
  { label: "(2) Import of services", igst: "₹0", cgst: "₹0", sgst: "₹0", cess: "₹0" },
  { label: "(3) Inward supplies liable to reverse charge", igst: "₹0", cgst: "₹8,325", sgst: "₹8,325", cess: "₹0", highlight: true },
  { label: "(4) Inward supplies from ISD", igst: "₹0", cgst: "₹0", sgst: "₹0", cess: "₹0" },
  { label: "(5) All other ITC", igst: "₹1,84,200", cgst: "₹15,24,887", sgst: "₹15,24,887", cess: "₹0", highlight: true },
  { label: "Total", igst: "₹1,84,200", cgst: "₹15,33,212", sgst: "₹15,33,212", cess: "₹0", total: true, highlight: true },
];

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

export default function FilingsPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0, background: "var(--bg)" }}>
      <ReturnHeader />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <WorkflowRail />
        <Canvas />
        <ActivityRail />
      </div>
    </div>
  );
}

/* --------------------------------- Return header --------------------------------- */

function ReturnHeader() {
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
        Filings › GST › GSTR-3B › Ramesh Textiles Pvt Ltd › Jul 2026
      </span>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <Monogram initials="RT" />
          <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
            <h1
              style={{
                margin: 0,
                fontSize: "var(--fs-h1)",
                lineHeight: "var(--lh-h1)",
                fontWeight: "var(--fw-semi)",
                letterSpacing: "var(--tr-h1)",
                color: "var(--text-primary)",
                whiteSpace: "nowrap",
              }}
            >
              GSTR-3B — July 2026
            </h1>
            <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-muted)" }}>
              Ramesh Textiles Pvt Ltd · <span className="mono" style={{ fontSize: 12 }}>29AAAAA0000A1Z5</span> · KA · Regular · Monthly
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flex: "none" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 10px",
              borderRadius: "var(--radius-chip)",
              background: "var(--warning-soft)",
              color: "var(--warning)",
              fontSize: 12,
              lineHeight: "16px",
              fontWeight: "var(--fw-medium)",
            }}
          >
            <AlertTriangleIcon size={12} />
            2 blockers
          </span>
          <VDiv />
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 10px",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-chip)",
              color: "var(--text-secondary)",
              fontSize: 12,
              lineHeight: "16px",
              fontWeight: "var(--fw-medium)",
            }}
          >
            <ClockIcon size={12} />
            Due in 7 days · 20 Aug 2026
          </span>
          <VDiv />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Draft saved 42s ago</span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Autosave enabled</span>
          </div>
          <VDiv />
          <HeaderBtn>Preview return PDF</HeaderBtn>
          <HeaderBtn>Send for client approval</HeaderBtn>
          <span title="Resolve 2 blockers first: 1 validation error, 1 unmatched ITC entry.">
            <button
              type="button"
              disabled
              style={{
                height: 32,
                padding: "0 14px",
                border: 0,
                borderRadius: "var(--radius-input)",
                background: "var(--accent)",
                color: "var(--on-accent)",
                font: `500 13px/20px var(--font-sans-v2)`,
                cursor: "not-allowed",
                opacity: 0.6,
              }}
            >
              File to GSTN
            </button>
          </span>
        </div>
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

function VDiv() {
  return <span style={{ width: 1, height: 24, background: "var(--border)" }} />;
}

/* --------------------------------- Workflow rail --------------------------------- */

function WorkflowRail() {
  return (
    <aside
      style={{
        width: 260,
        flex: "none",
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div style={{ padding: "20px 20px 16px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={LABEL}>Filing workflow</span>
        <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)" }} className="tabular">Step 5 of 6 · 82% complete</span>
        <div style={{ height: 4, background: "var(--border)", borderRadius: "var(--radius-pill)", overflow: "hidden" }}>
          <div style={{ width: "82%", height: 4, background: "var(--accent)" }} />
        </div>
      </div>
      <div style={{ flex: 1, padding: "16px 0", display: "flex", flexDirection: "column" }}>
        {STEPS.map((step, i) => (
          <StepNode key={i} step={step} isLast={i === STEPS.length - 1} isNextActive={STEPS[i + 1]?.status === "active"} />
        ))}
      </div>
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>
          History
        </a>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Started 10 Aug 2026</span>
      </div>
    </aside>
  );
}

function StepNode({ step, isLast, isNextActive }: { step: Step; isLast: boolean; isNextActive: boolean }) {
  const active = step.status === "active";
  const completed = step.status === "completed";
  const railColor = completed
    ? "var(--success)"
    : "var(--border)";

  return (
    <div
      style={{
        position: "relative",
        padding: active ? "12px 20px 12px 20px" : "10px 20px 10px 20px",
        background: active ? "var(--row-hover-accent)" : "transparent",
        display: "flex",
        gap: 12,
      }}
    >
      {active && (
        <span
          style={{
            position: "absolute",
            left: 0,
            top: 8,
            bottom: 8,
            width: 3,
            borderRadius: "0 3px 3px 0",
            background: "var(--accent)",
          }}
        />
      )}
      <div style={{ flex: "none", display: "flex", flexDirection: "column", alignItems: "center", width: 24 }}>
        <NodeCircle status={step.status} />
        {!isLast && (
          <span
            style={{
              flex: 1,
              width: 2,
              minHeight: 20,
              background: railColor,
              marginTop: 2,
              marginBottom: 2,
            }}
          />
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: isLast ? 0 : 8 }}>
        <span
          style={{
            display: "block",
            fontSize: 13,
            lineHeight: "18px",
            fontWeight: "var(--fw-medium)",
            color: active ? "var(--accent)" : completed ? "var(--text-primary)" : "var(--text-secondary)",
          }}
        >
          {step.label}
        </span>
        <span style={{ display: "block", marginTop: 2, fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>
          {step.subtitle}
        </span>
      </div>
    </div>
  );
}

function NodeCircle({ status }: { status: StepStatus }) {
  if (status === "completed") {
    return (
      <span
        style={{
          width: 24, height: 24, flex: "none", borderRadius: "var(--radius-pill)",
          background: "var(--success-soft)",
          color: "var(--success)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <CheckCircleIcon size={14} />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span
        style={{
          width: 24, height: 24, flex: "none", borderRadius: "var(--radius-pill)",
          background: "var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <span style={{ width: 8, height: 8, borderRadius: "var(--radius-pill)", background: "#fff" }} />
      </span>
    );
  }
  return (
    <span
      style={{
        width: 24, height: 24, flex: "none", borderRadius: "var(--radius-pill)",
        background: "var(--surface)",
        border: "2px solid var(--border-strong)",
      }}
    />
  );
}

/* --------------------------------- Canvas --------------------------------- */

function Canvas() {
  return (
    <main style={{ flex: 1, minWidth: 0, padding: 24, display: "flex", flexDirection: "column", gap: 20, overflow: "auto" }}>
      <SegmentedTabs />
      <p style={{ margin: 0, fontSize: 13, lineHeight: "20px", color: "var(--text-secondary)" }}>
        Verify the four blocks below match your ledgers. Blockers must be resolved before filing.
      </p>
      <HeadlineCards />
      <BlockersCard />
      <OutwardSuppliesTable />
      <ItcTable />
      <LedgerCard />
    </main>
  );
}

function SegmentedTabs() {
  const tabs = ["Summary", "Tables", "Ledger", "Notes"];
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
      <div style={{ height: 32, display: "flex", alignItems: "stretch", border: "1px solid var(--border)", borderRadius: "var(--radius-input)", overflow: "hidden" }}>
        {tabs.map((t, i) => (
          <button
            key={t}
            type="button"
            className="v2-focus-inset"
            style={{
              padding: "0 14px",
              border: 0,
              borderLeft: i === 0 ? "none" : "1px solid var(--border)",
              background: i === 0 ? "var(--accent-soft)" : "transparent",
              color: i === 0 ? "var(--accent)" : "var(--text-secondary)",
              font: `500 13px/20px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}

function HeadlineCards() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
      <HeadlineCard
        rail="var(--accent)"
        label="Outward tax (3.1a)"
        amount="₹42,68,780"
        amountColor="var(--text-primary)"
        subs={[
          "Taxable value: ₹2,37,15,450",
          "CGST: ₹19,17,236",
          "SGST: ₹19,17,236",
          "IGST: ₹4,34,308",
        ]}
      />
      <HeadlineCard
        rail="var(--success)"
        label="ITC available (4A)"
        amount="₹32,50,624"
        amountColor="var(--success)"
        subs={[
          "Matched ITC: ₹28,80,810",
          "Probable (pending): ₹8,62,421",
          "Ineligible (blocked): ₹0",
          "Reversal (4B): −₹4,92,607",
        ]}
      />
      <HeadlineCard
        rail="var(--warning)"
        label="Net payable in cash"
        amount="₹10,18,156"
        amountColor="var(--text-primary)"
        subs={[
          "Cash ledger balance: ₹4,50,000",
          <span key="short" style={{ color: "var(--danger)", fontWeight: 500 }}>Shortfall to fund: ₹5,68,156</span>,
          "Interest u/s 50: ₹0",
          "Late fee: ₹0",
        ]}
      />
    </div>
  );
}

function HeadlineCard({
  rail, label, amount, amountColor, subs,
}: {
  rail: string; label: string; amount: string; amountColor: string; subs: React.ReactNode[];
}) {
  return (
    <div
      style={{
        ...CARD,
        minHeight: 148,
        padding: "16px 16px 16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
        borderLeft: `3px solid ${rail}`,
      }}
    >
      <span style={LABEL}>{label}</span>
      <span
        className="tabular"
        style={{
          fontSize: "var(--fs-money-lg)",
          lineHeight: "var(--lh-money-lg)",
          fontWeight: "var(--fw-semi)",
          color: amountColor,
        }}
      >
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

function BlockersCard() {
  return (
    <div
      style={{
        borderRadius: "var(--radius-app-card)",
        border: "1px solid var(--danger)",
        borderLeft: "3px solid var(--danger)",
        background: "var(--danger-zone-bg)",
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <AlertTriangleIcon size={18} style={{ color: "var(--danger)" }} />
        <h2 style={{ margin: 0, fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--danger)" }}>
          2 blockers before you can file
        </h2>
        <span
          style={{
            padding: "2px 8px",
            borderRadius: "var(--radius-pill)",
            background: "var(--surface)",
            border: "1px solid var(--danger)",
            color: "var(--danger)",
            fontSize: 11,
            fontWeight: "var(--fw-semi)",
          }}
        >
          2 open
        </span>
      </div>
      <BlockerRow
        text="Invoice INV-2607-0142 has invalid HSN 998321 for supply of textiles — expected 6-digit HSN for turnover > ₹5 Cr"
      />
      <BlockerRow
        text="3 GSTR-2B entries missing from the purchase register (₹1,24,906.26) — record before filing or explicitly waive"
      />
    </div>
  );
}

function BlockerRow({ text }: { text: string }) {
  return (
    <div
      style={{
        minHeight: 48,
        padding: "10px 12px",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-chip)",
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}
    >
      <span
        style={{
          flex: "none",
          height: 20,
          padding: "0 6px",
          display: "flex",
          alignItems: "center",
          borderRadius: 4,
          background: "var(--danger-soft)",
          color: "var(--danger)",
          fontSize: 11,
          fontWeight: "var(--fw-semi)",
        }}
      >
        E
      </span>
      <span style={{ flex: 1, minWidth: 0, fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>
        {text}
      </span>
      <a href="#" className="v2-focus" style={{ flex: "none", fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>
        Resolve ↗
      </a>
    </div>
  );
}

function OutwardSuppliesTable() {
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
          {OUTWARD.map((r, i) => (
            <tr key={i} style={{ borderBottom: i === OUTWARD.length - 1 ? undefined : "1px solid var(--border)", background: r.total ? "var(--group-header)" : undefined }}>
              <Td bold={r.total}>{r.label}</Td>
              <TdRight bold={r.total}>{r.taxable}</TdRight>
              <TdRight bold={r.total}>{r.cgst}</TdRight>
              <TdRight bold={r.total}>{r.sgst}</TdRight>
              <TdRight bold={r.total}>{r.igst}</TdRight>
              <TdRight bold={r.total}>{r.cess}</TdRight>
            </tr>
          ))}
        </tbody>
      </table>
    </SectionCard>
  );
}

function ItcTable() {
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
          {ITC.map((r, i) => {
            const highlight = r.highlight;
            const color = highlight ? "var(--success)" : undefined;
            return (
              <tr key={i} style={{ borderBottom: i === ITC.length - 1 ? undefined : "1px solid var(--border)", background: r.total ? "var(--group-header)" : undefined }}>
                <Td bold={r.total}>{r.label}</Td>
                <TdRight bold={r.total} color={color}>{r.igst}</TdRight>
                <TdRight bold={r.total} color={color}>{r.cgst}</TdRight>
                <TdRight bold={r.total} color={color}>{r.sgst}</TdRight>
                <TdRight bold={r.total}>{r.cess}</TdRight>
              </tr>
            );
          })}
        </tbody>
      </table>
    </SectionCard>
  );
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
  return (
    <th style={{ padding: "10px 20px", textAlign: "left", ...LABEL }}>
      {children}
    </th>
  );
}
function ThRight({ children }: { children: React.ReactNode }) {
  return (
    <th style={{ padding: "10px 20px", textAlign: "right", ...LABEL }}>
      {children}
    </th>
  );
}
function Td({ children, bold }: { children: React.ReactNode; bold?: boolean }) {
  return (
    <td
      style={{
        padding: "10px 20px",
        fontSize: 13,
        lineHeight: "18px",
        color: "var(--text-primary)",
        fontWeight: bold ? "var(--fw-semi)" : "var(--fw-regular)",
      }}
    >
      {children}
    </td>
  );
}
function TdRight({ children, bold, color }: { children: React.ReactNode; bold?: boolean; color?: string }) {
  return (
    <td
      className="tabular"
      style={{
        padding: "10px 20px",
        textAlign: "right",
        fontSize: 13,
        lineHeight: "18px",
        color: color ?? "var(--text-primary)",
        fontWeight: bold ? "var(--fw-semi)" : "var(--fw-regular)",
      }}
    >
      {children}
    </td>
  );
}

function LedgerCard() {
  return (
    <SectionCard title="Ledger position after this filing">
      <div style={{ padding: 20, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>
        <LedgerCol
          label="Cash ledger (before)"
          amount="₹4,50,000"
          amountColor="var(--text-primary)"
          delta={{ text: "−₹4,50,000 consumed", tone: "danger" }}
          afterLabel="After"
          after="₹0"
        />
        <LedgerCol
          label="Credit ledger (before)"
          amount="₹32,50,624"
          amountColor="var(--text-primary)"
          delta={{ text: "−₹32,50,624 utilised", tone: "danger" }}
          afterLabel="After"
          after="₹0"
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={LABEL}>Shortfall</span>
          <span className="tabular" style={{ fontSize: "var(--fs-h1)", lineHeight: "var(--lh-h1)", fontWeight: "var(--fw-semi)", color: "var(--danger)" }}>
            ₹5,68,156
          </span>
          <button
            type="button"
            className="v2-focus"
            style={{
              marginTop: 6,
              height: 32,
              padding: "0 12px",
              border: "1px solid var(--accent)",
              borderRadius: "var(--radius-input)",
              background: "var(--surface)",
              color: "var(--accent)",
              font: `500 12px/16px var(--font-sans-v2)`,
              cursor: "pointer",
              alignSelf: "flex-start",
            }}
          >
            Generate PMT-06 challan
          </button>
        </div>
      </div>
    </SectionCard>
  );
}

function LedgerCol({
  label, amount, amountColor, delta, afterLabel, after,
}: {
  label: string; amount: string; amountColor: string;
  delta: { text: string; tone: "danger" | "warning" | "success" };
  afterLabel: string; after: string;
}) {
  const deltaBg = delta.tone === "danger" ? "var(--danger-soft)" : delta.tone === "warning" ? "var(--warning-soft)" : "var(--success-soft)";
  const deltaFg = delta.tone === "danger" ? "var(--danger)" : delta.tone === "warning" ? "var(--warning)" : "var(--success)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={LABEL}>{label}</span>
      <span className="tabular" style={{ fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: amountColor }}>
        {amount}
      </span>
      <span style={{ display: "inline-flex", alignSelf: "flex-start", padding: "2px 8px", borderRadius: "var(--radius-chip)", background: deltaBg, color: deltaFg, fontSize: 11, fontWeight: "var(--fw-medium)" }}>
        {delta.text}
      </span>
      <span style={{ marginTop: 4, fontSize: 11, color: "var(--text-muted)" }}>{afterLabel}</span>
      <span className="tabular" style={{ fontSize: 14, fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>{after}</span>
    </div>
  );
}

/* --------------------------------- Activity rail --------------------------------- */

type ActEntry = {
  dot: "success" | "warning" | "danger" | "accent" | "neutral";
  text: React.ReactNode;
  meta: string;
  sub?: React.ReactNode;
  quote?: string;
};
type ActGroup = { label: string; active?: boolean; entries: ActEntry[] };

const ACTIVITY_GROUPS: ActGroup[] = [
  {
    label: "Today · Wed 13 Aug 2026",
    active: true,
    entries: [
      {
        dot: "warning",
        text: <strong style={{ fontWeight: 500 }}>System flagged 2 blockers</strong>,
        sub: "Blocker 1: Invalid HSN on INV-2607-0142. Blocker 2: 3 unrecorded 2B entries totalling ₹1,24,906.26.",
        meta: "11:42 AM · Niyam auto-check",
      },
      { dot: "success", text: "Priya M. resolved validation flag R004 on 4 invoices", meta: "10:14 AM" },
    ],
  },
  {
    label: "Tue 12 Aug 2026",
    entries: [
      {
        dot: "accent",
        text: "Arjun D. approved reconciliation summary",
        quote: "Matched ₹28,80,810 across 10 invoices. Confirming 2 probable matches — see attached notes.",
        meta: "6:04 PM",
      },
      { dot: "neutral", text: "GSTR-2B pulled from GSTN · 15 entries", meta: "2:18 PM · GSP · WhiteBooks" },
    ],
  },
  {
    label: "Mon 11 Aug 2026",
    entries: [
      { dot: "neutral", text: "Purchase register uploaded by finance@ramesh… (312 rows)", meta: "10:04 AM" },
      { dot: "neutral", text: "Filing task created by Priya M.", meta: "9:32 AM" },
    ],
  },
];

function ActivityRail() {
  return (
    <aside
      style={{
        width: 340,
        flex: "none",
        background: "var(--surface)",
        borderLeft: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div style={{ height: 56, padding: "0 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0, fontSize: 18, lineHeight: "24px", fontWeight: "var(--fw-semi)", color: "var(--text-primary)" }}>Activity</h2>
        <div style={{ height: 28, display: "flex", border: "1px solid var(--border)", borderRadius: "var(--radius-input)", overflow: "hidden" }}>
          <button
            type="button"
            className="v2-focus-inset"
            style={{
              padding: "0 10px",
              border: 0,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              font: `500 12px/16px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            All
          </button>
          <button
            type="button"
            className="v2-hover-tint v2-focus-inset"
            style={{
              padding: "0 10px",
              border: 0,
              borderLeft: "1px solid var(--border)",
              background: "transparent",
              color: "var(--text-secondary)",
              font: `500 12px/16px var(--font-sans-v2)`,
              cursor: "pointer",
            }}
          >
            Blockers
          </button>
        </div>
      </div>

      <OwnerBlock />

      <div style={{ flex: 1, overflow: "auto" }}>
        {ACTIVITY_GROUPS.map((g) => (
          <div key={g.label}>
            <div
              style={{
                height: 32,
                padding: "0 20px",
                background: g.active ? "var(--accent-soft)" : "var(--bg)",
                display: "flex",
                alignItems: "center",
                fontSize: 11,
                fontWeight: "var(--fw-medium)",
                letterSpacing: "var(--tr-label)",
                textTransform: "uppercase",
                color: g.active ? "var(--accent)" : "var(--text-muted)",
              }}
            >
              {g.label}
            </div>
            <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16, borderLeft: "1px solid transparent" }}>
              {g.entries.map((e, i) => (
                <ActivityEntry key={i} e={e} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div style={{ height: 56, padding: "12px 16px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="text"
          placeholder="Add a note or @mention a teammate…"
          style={{
            flex: 1,
            height: 32,
            padding: "0 10px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--bg)",
            outline: 0,
            font: `400 13px/20px var(--font-sans-v2)`,
            color: "var(--text-primary)",
          }}
        />
        <button
          type="button"
          aria-label="Send"
          className="v2-btn-primary v2-focus"
          style={{
            width: 32, height: 32,
            display: "flex", alignItems: "center", justifyContent: "center",
            border: 0, borderRadius: "var(--radius-input)",
            background: "var(--accent)",
            color: "var(--on-accent)",
            cursor: "pointer",
          }}
        >
          <ArrowUpIcon size={14} />
        </button>
      </div>
    </aside>
  );
}

function OwnerBlock() {
  return (
    <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={LABEL}>Owned by</span>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Reassign</a>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          style={{
            width: 32, height: 32, flex: "none",
            borderRadius: "var(--radius-pill)",
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 12, fontWeight: "var(--fw-semi)",
          }}
        >
          AD
        </span>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 14, lineHeight: "18px", fontWeight: "var(--fw-medium)", color: "var(--text-primary)" }}>Arjun Desai</span>
          <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>Partner · Reviewer</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          {["PM", "KS", "RS"].map((i, idx) => (
            <span
              key={i}
              style={{
                width: 24, height: 24,
                marginLeft: idx === 0 ? 0 : -6,
                borderRadius: "var(--radius-pill)",
                background: "var(--row-hover)",
                color: "var(--text-secondary)",
                border: "2px solid var(--surface)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 10, fontWeight: "var(--fw-semi)",
              }}
            >
              {i}
            </span>
          ))}
          <span
            style={{
              width: 24, height: 24, marginLeft: -6,
              borderRadius: "var(--radius-pill)",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, fontWeight: "var(--fw-semi)",
            }}
          >
            +2
          </span>
        </div>
        <a href="#" className="v2-focus" style={{ fontSize: 12, fontWeight: "var(--fw-medium)", color: "var(--accent)", textDecoration: "none" }}>Invite</a>
      </div>
    </div>
  );
}

function ActivityEntry({ e }: { e: ActEntry }) {
  const dotColor =
    e.dot === "success" ? "var(--success)" :
    e.dot === "warning" ? "var(--warning)" :
    e.dot === "danger" ? "var(--danger)" :
    e.dot === "accent" ? "var(--accent)" : "var(--border-strong)";
  return (
    <div style={{ position: "relative", paddingLeft: 20, borderLeft: "1px solid var(--border)", marginLeft: 4, display: "flex", flexDirection: "column", gap: 4 }}>
      <span
        style={{
          position: "absolute",
          left: -5,
          top: 4,
          width: 9,
          height: 9,
          borderRadius: "var(--radius-pill)",
          background: dotColor,
          boxShadow: "0 0 0 3px var(--surface)",
        }}
      />
      <span style={{ fontSize: 13, lineHeight: "18px", color: "var(--text-primary)" }}>{e.text}</span>
      {e.sub && (
        <span style={{ fontSize: 12, lineHeight: "16px", color: "var(--text-secondary)", paddingLeft: 8, borderLeft: "2px solid var(--border)" }}>
          {e.sub}
        </span>
      )}
      {e.quote && (
        <div
          style={{
            marginTop: 4,
            padding: 10,
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-input)",
            background: "var(--bg)",
            fontSize: 12,
            lineHeight: "16px",
            color: "var(--text-secondary)",
          }}
        >
          “{e.quote}”
        </div>
      )}
      <span style={{ fontSize: 11, lineHeight: "14px", color: "var(--text-muted)" }}>{e.meta}</span>
    </div>
  );
}
