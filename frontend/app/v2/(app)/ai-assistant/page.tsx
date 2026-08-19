"use client";

import { useState, type CSSProperties } from "react";
import {
  ArrowUpIcon,
  DownloadIcon,
  PlusIcon,
  SearchIcon,
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
      </div>
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
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
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

