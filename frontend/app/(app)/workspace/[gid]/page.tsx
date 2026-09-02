"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { BUCKET_DESCRIPTIONS, BUCKET_LABELS, CDN_DISCLAIMER } from "@/lib/constants";
import {
  ArithmeticPanel,
  BlockersList,
  ITCCell,
  ScoreCell,
} from "@/components/atoms";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import { ConnectionsPanel } from "@/components/ConnectionsPanel";
import { DeliveryPanel } from "@/components/DeliveryPanel";
import { SupplierChasePanel } from "@/components/SupplierChasePanel";
import { FilingsTab } from "@/components/FilingsTab";
import { OcrPanel } from "@/components/OcrPanel";
import { formatDateIN, formatPeriod, formatTimestampIN } from "@/lib/format-date";
import { bucketTint } from "@/lib/design-tokens";
import type {
  Flag,
  GstinClientInfo,
  MatchResult,
  ReadinessResponse,
  ReconResponse,
} from "@/lib/types";


type Tab = "invoices" | "reconciliation" | "returns" | "filings" | "ocr";
type Bucket = "matched" | "probable" | "supplier_default" | "missing_entry";


export default function WorkspacePage() {
  const params = useParams<{ gid: string }>();
  const search = useSearchParams();
  const gid = params.gid;
  const period = search.get("period") || "";
  const returnType = (search.get("return_type") || "GSTR1") as "GSTR1" | "GSTR3B";
  const initialTab = (search.get("tab") as Tab) || "returns";
  // Passed via URL from the command-center drill link so the page can
  // greet the CA with the client's trade name — no extra API call.
  const clientName = search.get("client") || "Client workspace";
  const gstin = search.get("gstin") || "";
  const [tab, setTab] = useState<Tab>(initialTab);

  return (
    <>
      <PageHeader
        title={clientName}
        context={
          <span className="inline-flex items-center gap-3">
            {gstin && <span className="font-mono">{gstin}</span>}
            <span>·</span>
            <span>{returnType}</span>
            <span>·</span>
            <span>{formatPeriod(period)}</span>
          </span>
        }
      />

      <ConnectionsPanel gstinProfileId={gid} />

      <div className="flex gap-8 border-b border-rule -mx-6 px-6">
        {(["invoices", "reconciliation", "returns", "filings", "ocr"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              "px-1 py-4 text-lg capitalize border-b-2 -mb-px transition-colors duration-fast " +
              (tab === t
                ? "border-accent text-ink font-semibold"
                : "border-transparent text-ink-muted hover:text-ink")
            }
            data-testid={`tab-${t}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "invoices" && <InvoicesTab gid={gid} period={period} />}
      {tab === "reconciliation" && <ReconciliationTab gid={gid} period={period} />}
      {tab === "returns" && (
        <ReturnsTab gid={gid} period={period} returnType={returnType} />
      )}
      {tab === "filings" && (
        <FilingsTab gid={gid} period={period} returnType={returnType} />
      )}
      {tab === "ocr" && <OcrPanel gstinProfileId={gid} />}
    </>
  );
}


// ---------------------------------------------------------------------------
// INVOICES TAB (flags list)
// ---------------------------------------------------------------------------


function InvoicesTab({ gid, period }: { gid: string; period: string }) {
  const [flags, setFlags] = useState<Flag[] | null>(null);
  useEffect(() => {
    api<Flag[]>(`/gstins/${gid}/flags?period=${period}`).then(setFlags);
  }, [gid, period]);

  async function resolve(f: Flag) {
    await api(`/flags/${f.id}/resolve`, {
      method: "POST",
      body: { resolved: true },
    });
    setFlags((prev) =>
      prev ? prev.map((x) => (x.id === f.id ? { ...x, resolved: true } : x)) : prev
    );
  }

  if (!flags) return <SkeletonTable rows={5} cols={5} />;

  const columns: Column<Flag>[] = [
    {
      key: "rule",
      header: "Rule",
      cell: (f) => <span className="font-mono">{f.rule_code}</span>,
      sortable: true,
      sortValue: (f) => f.rule_code,
      width: "5rem",
    },
    {
      key: "sev",
      header: "Severity",
      cell: (f) => <SeverityPill severity={f.severity} />,
      sortable: true,
      sortValue: (f) => f.severity,
      width: "6rem",
    },
    {
      key: "msg",
      header: "Message",
      cell: (f) => <span className="text-ink">{f.message}</span>,
    },
    {
      key: "resolved",
      header: "Resolved",
      cell: (f) =>
        f.resolved ? (
          <span className="text-green-fg font-semibold">Yes</span>
        ) : (
          <span className="text-ink-muted">No</span>
        ),
      width: "6rem",
    },
    {
      key: "action",
      header: "",
      cell: (f) =>
        !f.resolved ? (
          <button
            onClick={() => resolve(f)}
            className="text-accent hover:text-accent-hover hover:underline text-xs font-semibold"
          >
            Mark resolved
          </button>
        ) : null,
      align: "right",
      width: "8rem",
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={flags}
      rowKey={(f) => f.id}
      initialSort={{ key: "sev", dir: "asc" }}
      emptyState={
        <EmptyState
          title="No flags for this period"
          body={`Nothing to fix. Either no invoices exist for ${formatPeriod(period)} yet, or every invoice passed validation. Import a purchase register from the Imports tab to bring more in.`}
          action={{ label: "Go to Imports", href: "/imports" }}
        />
      }
    />
  );
}


function SeverityPill({ severity }: { severity: "error" | "warning" }) {
  const cls =
    severity === "error"
      ? "bg-red-bg text-red-fg"
      : "bg-amber-bg text-amber-fg";
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-sm ${cls}`}>
      {severity}
    </span>
  );
}


// ---------------------------------------------------------------------------
// RECONCILIATION TAB
// ---------------------------------------------------------------------------


function ReconciliationTab({ gid, period }: { gid: string; period: string }) {
  const [recon, setRecon] = useState<ReconResponse | null>(null);
  const [matches, setMatches] = useState<MatchResult[] | null>(null);
  const [bucket, setBucket] = useState<Bucket>("supplier_default");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setRecon(null);
    api<ReconResponse>(`/gstins/${gid}/reconciliation?period=${period}`)
      .then(setRecon)
      .catch(() =>
        setRecon({
          run_id: null, period, status: null, summary: {},
          rule_pack_version: null, finished_at: null,
        })
      );
  }, [gid, period]);

  useEffect(() => {
    if (!recon?.run_id) {
      setMatches([]);
      return;
    }
    setMatches(null);
    api<MatchResult[]>(
      `/reconciliation-runs/${recon.run_id}/matches?bucket=${bucket}`
    ).then(setMatches);
  }, [recon?.run_id, bucket]);

  async function confirm(id: string) {
    try {
      await api(`/match-results/${id}/confirm`, { method: "POST" });
      setMessage("Match confirmed. Audit row recorded.");
      if (recon?.run_id) {
        setMatches(null);
        api<MatchResult[]>(
          `/reconciliation-runs/${recon.run_id}/matches?bucket=${bucket}`
        ).then(setMatches);
      }
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function reject(id: string) {
    try {
      await api(`/match-results/${id}/reject`, { method: "POST" });
      setMessage("Match rejected. Audit row recorded.");
      if (recon?.run_id) {
        setMatches(null);
        api<MatchResult[]>(
          `/reconciliation-runs/${recon.run_id}/matches?bucket=${bucket}`
        ).then(setMatches);
      }
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function markReviewed(id: string, reason?: string) {
    try {
      await api(`/match-results/${id}/mark-reviewed`, {
        method: "POST",
        body: { reason: reason ?? null },
      });
      setMessage("Row marked as reviewed.");
      setMatches((prev) =>
        prev
          ? prev.map((m) =>
              m.id === id
                ? {
                    ...m,
                    confirmed_at: new Date().toISOString(),
                    context: {
                      ...m.context,
                      reviewed_at: new Date().toISOString(),
                      ...(reason ? { reviewed_reason: reason } : {}),
                    },
                  }
                : m,
            )
          : prev,
      );
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e));
    }
  }

  if (!recon) return <SkeletonTable rows={2} cols={4} />;
  if (!recon.run_id) {
    return (
      <EmptyState
        title="No reconciliation run yet"
        body={`No completed reconciliation exists for ${formatPeriod(period)}. Upload a GSTR-2B JSON from Imports, then trigger a run — matched, probable, and residual buckets appear here.`}
        action={{ label: "Go to Imports", href: "/imports" }}
      />
    );
  }

  const s = recon.summary || {};
  return (
    <div className="space-y-4">
      {message && (
        <p className="text-sm bg-green-bg border border-rule text-green-fg rounded-md px-3 py-2">
          {message}
        </p>
      )}

      {/* 4-bucket summary */}
      <div className="grid grid-cols-4 gap-3">
        {(["matched", "probable", "supplier_default", "missing_entry"] as const).map(
          (b) => {
            const isSelected = bucket === b;
            const tint = bucketTint[b];
            const bucketData = (s as any)[b] ?? {};
            const paise =
              b === "matched" || b === "probable"
                ? (bucketData.paise_claimable ?? bucketData.paise ?? 0)
                : (bucketData.paise ?? 0);
            return (
              <button
                key={b}
                onClick={() => setBucket(b)}
                className={
                  "text-left p-3 rounded-md border transition-colors duration-fast " +
                  (isSelected
                    ? "border-accent bg-accent-tint"
                    : "border-rule bg-paper-raised hover:border-rule-strong")
                }
                data-testid={`bucket-${b}`}
              >
                <div
                  className="text-xs uppercase tracking-wide font-semibold"
                  style={{ color: tint.fg }}
                >
                  {BUCKET_LABELS[b]}
                </div>
                <div className="text-xl font-mono font-semibold mt-2 text-ink">
                  {bucketData.count ?? 0}
                </div>
                <div className="text-xs mt-1">
                  <ITCCell paise={paise} />
                </div>
                {(b === "matched" || b === "probable") &&
                  (bucketData.paise_not_available ?? 0) > 0 && (
                    <div className="text-xs mt-1 text-amber-fg font-semibold">
                      +<ITCCell paise={bucketData.paise_not_available} /> blocked
                    </div>
                  )}
              </button>
            );
          }
        )}
      </div>

      {/* CDN informational callout */}
      {(s as any).cdn?.count > 0 && (
        <div className="text-xs bg-paper-raised border border-rule rounded-md px-3 py-2 text-ink-muted">
          <span className="font-semibold text-ink">{(s as any).cdn.count}</span> credit/debit note
          {(s as any).cdn.count !== 1 ? "s" : ""} found in 2B (
          <ITCCell paise={(s as any).cdn.paise} />
          ) — not yet applied to ITC. Full CDN adjustment is a P2 feature.
        </div>
      )}

      <p className="text-xs text-ink">
        Claimable ITC figures shown above and below:{" "}
        <span className="font-semibold">{CDN_DISCLAIMER}</span>.
      </p>

      <div className="bg-paper-raised border border-rule rounded-md p-4">
        <p className="text-sm text-ink-muted mb-3">{BUCKET_DESCRIPTIONS[bucket]}</p>
        {matches === null && <SkeletonTable rows={3} cols={2} />}
        {matches !== null && (
          <MatchesList
            matches={matches}
            bucket={bucket}
            onConfirm={confirm}
            onReject={reject}
            onMarkReviewed={markReviewed}
            onMatchContextPatch={(matchId, patch) =>
              setMatches((prev) =>
                prev
                  ? prev.map((m) =>
                      m.id === matchId
                        ? { ...m, context: { ...m.context, ...patch } }
                        : m,
                    )
                  : prev,
              )
            }
          />
        )}
      </div>
    </div>
  );
}


function MatchesList({
  matches,
  bucket,
  onConfirm,
  onReject,
  onMarkReviewed,
  onMatchContextPatch,
}: {
  matches: MatchResult[];
  bucket: Bucket;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
  onMarkReviewed: (id: string, reason?: string) => void;
  onMatchContextPatch?: (
    matchId: string,
    patch: Partial<MatchResult["context"]>,
  ) => void;
}) {
  if (matches.length === 0) {
    return (
      <p className="text-sm text-ink-muted italic p-4 text-center" data-testid="empty-bucket">
        No rows in this bucket.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {matches.map((m) => (
        <MatchRow
          key={m.id}
          match={m}
          bucket={bucket}
          onConfirm={onConfirm}
          onReject={onReject}
          onMarkReviewed={onMarkReviewed}
          onMatchContextPatch={onMatchContextPatch}
        />
      ))}
    </div>
  );
}


function MatchRow({
  match: m,
  bucket,
  onConfirm,
  onReject,
  onMarkReviewed,
  onMatchContextPatch,
}: {
  match: MatchResult;
  bucket: Bucket;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
  onMarkReviewed: (id: string, reason?: string) => void;
  onMatchContextPatch?: (id: string, patch: Partial<MatchResult["context"]>) => void;
}) {
  const ctx = m.context;
  const isReviewed = !!ctx.reviewed_at || !!m.confirmed_at;
  const itcBlocked = ctx.b2b_itc_available === false;

  return (
    <div
      className={
        "border rounded-md p-3 " +
        (m.rejected
          ? "border-red-fg/30 bg-red-bg"
          : isReviewed && bucket !== "probable"
            ? "border-green-fg/30 bg-green-bg"
            : "border-rule bg-paper")
      }
      data-testid={`match-row-${m.id}`}
    >
      {/* Header row: supplier + status badges */}
      <div className="flex items-start gap-2 flex-wrap mb-2">
        <span className="font-mono text-xs font-semibold text-ink">
          {ctx.supplier_gstin ?? "—"}
        </span>
        {m.rejected && (
          <span className="text-xs text-red-fg bg-red-bg border border-red-fg/30 px-1.5 py-0.5 rounded-sm font-semibold">
            rejected
          </span>
        )}
        {bucket === "probable" && m.confirmed_at && !m.rejected && (
          <span className="text-xs text-green-fg bg-green-bg border border-green-fg/30 px-1.5 py-0.5 rounded-sm font-semibold">
            confirmed
          </span>
        )}
        {(bucket === "supplier_default" || bucket === "missing_entry") && isReviewed && (
          <span className="text-xs text-green-fg bg-green-bg border border-green-fg/30 px-1.5 py-0.5 rounded-sm font-semibold">
            reviewed
          </span>
        )}
        {bucket === "matched" && itcBlocked && (
          <span className="text-xs text-amber-fg bg-amber-bg px-1.5 py-0.5 rounded-sm font-semibold">
            ITC blocked
          </span>
        )}
        {bucket === "probable" && (
          <span className="text-xs text-ink-muted ml-auto font-mono">
            confidence {m.confidence.toFixed(2)}
          </span>
        )}
      </div>

      {/* Invoice detail rows */}
      <div className="grid grid-cols-[4rem_1fr] gap-x-3 gap-y-1 text-xs mb-3">
        {/* Register side */}
        {ctx.register_invoice_number && (
          <>
            <span className="text-ink-muted font-semibold pt-0.5">Register</span>
            <InvoiceLine
              number={ctx.register_invoice_number}
              date={ctx.register_invoice_date}
              paise={ctx.register_total_paise}
            />
          </>
        )}
        {/* 2B side */}
        {ctx.b2b_invoice_number && (
          <>
            <span className="text-ink-muted font-semibold pt-0.5">2B</span>
            <InvoiceLine
              number={ctx.b2b_invoice_number}
              date={ctx.b2b_invoice_date}
              paise={ctx.b2b_total_paise}
              itcBlocked={itcBlocked}
            />
          </>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap">
        {bucket === "probable" && !m.confirmed_at && !m.rejected && (
          <>
            <button
              onClick={() => onConfirm(m.id)}
              className="px-3 py-1 text-xs bg-accent text-paper-raised font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast"
              data-testid="confirm-match"
            >
              Confirm match
            </button>
            <button
              onClick={() => onReject(m.id)}
              className="px-3 py-1 text-xs bg-paper-raised border border-rule text-ink rounded-sm hover:border-rule-strong transition-colors duration-fast"
            >
              Reject
            </button>
          </>
        )}
        {(bucket === "supplier_default" || bucket === "missing_entry") && !isReviewed && (
          <button
            onClick={() => onMarkReviewed(m.id)}
            className="px-3 py-1 text-xs bg-paper-raised border border-rule text-ink rounded-sm hover:border-rule-strong transition-colors duration-fast"
            data-testid="mark-reviewed"
          >
            Mark reviewed
          </button>
        )}
        {ctx.reviewed_reason && (
          <span className="text-xs text-ink-muted italic">
            {ctx.reviewed_reason}
          </span>
        )}
      </div>

      {/* Supplier chase panel for supplier_default */}
      {bucket === "supplier_default" && (
        <div className="mt-3">
          <SupplierChasePanel
            match={m}
            onLocalUpdate={
              onMatchContextPatch
                ? (patch) => onMatchContextPatch(m.id, patch)
                : undefined
            }
          />
        </div>
      )}
    </div>
  );
}


function InvoiceLine({
  number,
  date,
  paise,
  itcBlocked,
}: {
  number: string;
  date?: string;
  paise?: number;
  itcBlocked?: boolean;
}) {
  return (
    <span className={itcBlocked ? "text-amber-fg" : "text-ink"}>
      <span className="font-mono">{number}</span>
      {date && (
        <span className="text-ink-muted ml-2">{formatDateIN(date)}</span>
      )}
      {paise !== undefined && (
        <span className="ml-2">
          <ITCCell paise={paise} />
        </span>
      )}
      {itcBlocked && (
        <span className="ml-1 text-amber-fg">(blocked)</span>
      )}
    </span>
  );
}


// ---------------------------------------------------------------------------
// RETURNS TAB (score hero + blockers + arithmetic drawer)
// ---------------------------------------------------------------------------


function ReturnsTab({
  gid,
  period,
  returnType,
}: {
  gid: string;
  period: string;
  returnType: "GSTR1" | "GSTR3B";
}) {
  const [snap, setSnap] = useState<ReadinessResponse | null>(null);
  const [clientInfo, setClientInfo] = useState<GstinClientInfo | null>(null);
  const [showMath, setShowMath] = useState(false);

  useEffect(() => {
    api<ReadinessResponse>(
      `/gstins/${gid}/readiness?return_type=${returnType}&period=${period}`
    ).then(setSnap);
  }, [gid, period, returnType]);

  useEffect(() => {
    // Client details for the DeliveryPanel prefill. Fetched once per
    // (gid) rather than on every panel-open so a rapid tab switch does
    // not thrash the endpoint.
    api<GstinClientInfo>(`/gstins/${gid}/client`).then(setClientInfo).catch(() => {
      // Non-fatal — the DeliveryPanel just runs without prefill.
      setClientInfo(null);
    });
  }, [gid]);

  if (!snap) return <SkeletonTable rows={2} cols={2} />;

  return (
    <div className="space-y-4">
      <div className="bg-paper-raised border border-rule rounded-md p-4 flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowMath((v) => !v)}
            className="cursor-pointer hover:opacity-90 transition-opacity duration-fast rounded-md"
            data-testid="score-value"
            aria-label={`Score ${snap.score ?? "not yet scored"} — click for arithmetic`}
          >
            <ScoreCell score={snap.score} size="lg" />
          </button>
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-muted font-semibold">
              {returnType} · {formatPeriod(period)}
            </div>
            <div className="text-xs text-ink-muted mt-1">
              Click score to {showMath ? "hide" : "show"} arithmetic (stored math).
            </div>
          </div>
        </div>
        <div className="text-xs text-ink-muted ml-auto text-right">
          Rule pack{" "}
          <span className="font-mono text-ink">
            {snap.rule_pack_version || "—"}
          </span>
          <br />
          Computed{" "}
          <span className="font-mono text-ink">
            {snap.computed_at ? formatTimestampIN(snap.computed_at) : "never"}
          </span>
        </div>
      </div>

      {showMath && (
        <div
          className="bg-paper-raised border border-rule rounded-md p-4"
          data-testid="arithmetic-panel"
        >
          <ArithmeticPanel arithmetic={snap.arithmetic} />
        </div>
      )}

      <div>
        <h2 className="text-sm font-semibold text-ink mb-2">Blockers</h2>
        <BlockersList blockers={snap.blockers} />
      </div>

      {/* Client 2-pager delivery — sits at the tail of the returns tab
          so the CA hits it after reviewing score + blockers, in that
          order. Only rendered once a snapshot exists (guards against
          the "generate narration with no facts" 409). */}
      {snap.snapshot_id && (
        <DeliveryPanel
          gstinProfileId={gid}
          period={period}
          returnType={returnType}
          clientId={clientInfo?.client_id}
          clientWhatsappNumber={clientInfo?.whatsapp_number ?? undefined}
          clientDefaultLanguage={
            (clientInfo?.language as "en" | "hi" | "kn" | "mr" | undefined) ?? "en"
          }
        />
      )}
    </div>
  );
}
