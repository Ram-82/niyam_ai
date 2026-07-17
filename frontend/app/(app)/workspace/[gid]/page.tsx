"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { BUCKET_DESCRIPTIONS, BUCKET_LABELS, CDN_DISCLAIMER } from "@/lib/constants";
import {
  ArithmeticPanel,
  BlockersList,
  ITCCell,
  ITCHeader,
  NearMissReview,
  ScoreCell,
} from "@/components/atoms";
import type {
  Flag,
  MatchResult,
  ReadinessResponse,
  ReconResponse,
} from "@/lib/types";


type Tab = "invoices" | "reconciliation" | "returns";


export default function WorkspacePage() {
  const params = useParams<{ gid: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const gid = params.gid;
  const period = search.get("period") || "";
  const returnType = (search.get("return_type") || "GSTR1") as "GSTR1" | "GSTR3B";
  const initialTab = (search.get("tab") as Tab) || "returns";
  const [tab, setTab] = useState<Tab>(initialTab);

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-4">
        <h1 className="text-xl font-semibold">Workspace</h1>
        <span className="text-sm text-neutral-500 font-mono">
          gstin_profile {gid.slice(0, 8)}… &middot; {returnType} &middot; {period}
        </span>
      </div>

      <div className="flex gap-2 border-b border-neutral-200">
        {(["invoices", "reconciliation", "returns"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              "px-3 py-1 text-sm capitalize " +
              (tab === t
                ? "border-b-2 border-blue-600 font-medium"
                : "text-neutral-600")
            }
            data-testid={`tab-${t}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "invoices" && <InvoicesTab gid={gid} period={period} />}
      {tab === "reconciliation" && (
        <ReconciliationTab gid={gid} period={period} />
      )}
      {tab === "returns" && (
        <ReturnsTab gid={gid} period={period} returnType={returnType} />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// INVOICES TAB
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

  if (!flags) return <p className="text-sm text-neutral-500">Loading…</p>;

  return (
    <table className="w-full text-sm border border-neutral-200 bg-white">
      <thead className="bg-neutral-50 text-left">
        <tr>
          <th className="p-2">Rule</th>
          <th className="p-2">Severity</th>
          <th className="p-2">Message</th>
          <th className="p-2">Resolved</th>
          <th className="p-2"></th>
        </tr>
      </thead>
      <tbody>
        {flags.map((f, i) => (
          <tr key={f.id} className={i % 2 ? "bg-neutral-50" : ""}>
            <td className="p-2 font-mono">{f.rule_code}</td>
            <td className="p-2">{f.severity}</td>
            <td className="p-2">{f.message}</td>
            <td className="p-2">{f.resolved ? "yes" : "no"}</td>
            <td className="p-2 text-right">
              {!f.resolved && (
                <button
                  onClick={() => resolve(f)}
                  className="text-blue-700 hover:underline text-xs"
                >
                  Mark resolved
                </button>
              )}
            </td>
          </tr>
        ))}
        {flags.length === 0 && (
          <tr>
            <td colSpan={5} className="p-4 text-center text-neutral-500">
              No flags for this period.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}


// ---------------------------------------------------------------------------
// RECONCILIATION TAB
// ---------------------------------------------------------------------------


function ReconciliationTab({ gid, period }: { gid: string; period: string }) {
  const [recon, setRecon] = useState<ReconResponse | null>(null);
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [bucket, setBucket] = useState<
    "matched" | "probable" | "supplier_default" | "missing_entry"
  >("supplier_default");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<ReconResponse>(`/gstins/${gid}/reconciliation?period=${period}`)
      .then(setRecon)
      .catch(() => setRecon({
        run_id: null, period, status: null, summary: {},
        rule_pack_version: null, finished_at: null,
      }));
  }, [gid, period]);

  useEffect(() => {
    if (!recon?.run_id) {
      setMatches([]);
      return;
    }
    api<MatchResult[]>(
      `/reconciliation-runs/${recon.run_id}/matches?bucket=${bucket}`
    ).then(setMatches);
  }, [recon?.run_id, bucket]);

  async function confirm(id: string) {
    try {
      await api(`/match-results/${id}/confirm`, { method: "POST" });
      setMessage("Match confirmed. Audit row recorded.");
      // Re-fetch matches to reflect the promotion.
      if (recon?.run_id) {
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
        api<MatchResult[]>(
          `/reconciliation-runs/${recon.run_id}/matches?bucket=${bucket}`
        ).then(setMatches);
      }
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : String(e));
    }
  }

  if (!recon) return <p className="text-sm text-neutral-500">Loading…</p>;

  const s = recon.summary || {};
  return (
    <div className="space-y-4">
      {message && (
        <p className="text-sm bg-green-50 border border-green-200 rounded p-2">
          {message}
        </p>
      )}

      {/* 4-bucket summary */}
      <div className="grid grid-cols-4 gap-3">
        {(
          ["matched", "probable", "supplier_default", "missing_entry"] as const
        ).map((b) => (
          <button
            key={b}
            onClick={() => setBucket(b)}
            className={
              "text-left p-3 border rounded " +
              (bucket === b
                ? "border-blue-600 bg-blue-50"
                : "border-neutral-200 bg-white")
            }
            data-testid={`bucket-${b}`}
          >
            <div className="text-xs uppercase text-neutral-500">
              {BUCKET_LABELS[b]}
            </div>
            <div className="text-lg font-semibold mt-1">
              {(s as any)[b]?.count ?? 0}
            </div>
            <div className="text-xs mt-1">
              <ITCCell paise={(s as any)[b]?.paise ?? 0} />
            </div>
          </button>
        ))}
      </div>

      <p className="text-xs text-neutral-500">
        All ITC figures shown above and below: <b>{CDN_DISCLAIMER}</b>.
      </p>

      <div className="bg-white border border-neutral-200 rounded p-3">
        <p className="text-sm mb-2">{BUCKET_DESCRIPTIONS[bucket]}</p>
        <MatchesTable
          matches={matches}
          bucket={bucket}
          onConfirm={confirm}
          onReject={reject}
        />
      </div>
    </div>
  );
}


function MatchesTable({
  matches,
  bucket,
  onConfirm,
  onReject,
}: {
  matches: MatchResult[];
  bucket: string;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}) {
  if (matches.length === 0) {
    return (
      <p className="text-sm text-neutral-500">No rows in this bucket.</p>
    );
  }
  return (
    <div className="space-y-3">
      {matches.map((m) => (
        <div key={m.id} className="border border-neutral-200 rounded p-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-mono text-xs">{m.id.slice(0, 8)}…</span>
            <span className="text-neutral-500">
              confidence {m.confidence.toFixed(2)}
            </span>
            {m.rejected && (
              <span className="text-xs text-red-700 bg-red-50 px-1 rounded">
                rejected
              </span>
            )}
            <span className="ml-auto flex gap-2">
              {bucket === "probable" && !m.confirmed_at && !m.rejected && (
                <>
                  <button
                    onClick={() => onConfirm(m.id)}
                    className="px-2 py-1 text-xs bg-blue-600 text-white rounded"
                    data-testid="confirm-match"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => onReject(m.id)}
                    className="px-2 py-1 text-xs bg-neutral-200 rounded"
                  >
                    Reject
                  </button>
                </>
              )}
            </span>
          </div>

          {bucket === "supplier_default" && (
            <div className="mt-3">
              <NearMissReview
                nearMisses={m.context.near_misses || []}
                onConfirm={() => {
                  /* P2: this triggers a manual match creation flow */
                }}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}


// ---------------------------------------------------------------------------
// RETURNS TAB (readiness score + blockers + arithmetic drawer)
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
  const [showMath, setShowMath] = useState(false);

  useEffect(() => {
    api<ReadinessResponse>(
      `/gstins/${gid}/readiness?return_type=${returnType}&period=${period}`
    ).then(setSnap);
  }, [gid, period, returnType]);

  if (!snap) return <p className="text-sm text-neutral-500">Loading…</p>;

  return (
    <div className="space-y-4">
      <div className="bg-white border border-neutral-200 rounded p-4 flex items-center gap-6">
        <div>
          <div className="text-xs uppercase text-neutral-500">
            {returnType} · {period}
          </div>
          <button
            onClick={() => setShowMath((v) => !v)}
            className="mt-1 text-3xl font-bold hover:underline"
            data-testid="score-value"
            title="Click to see the persisted arithmetic"
          >
            <ScoreCell score={snap.score} />
          </button>
          <div className="text-xs text-neutral-500 mt-1">
            Click score to {showMath ? "hide" : "show"} arithmetic (stored math).
          </div>
        </div>
        <div className="text-xs text-neutral-500 ml-auto">
          Rule pack{" "}
          <span className="font-mono">
            {snap.rule_pack_version || "—"}
          </span>
          <br />
          Computed{" "}
          <span className="font-mono">
            {snap.computed_at
              ? new Date(snap.computed_at).toISOString()
              : "never"}
          </span>
        </div>
      </div>

      {showMath && (
        <div
          className="bg-white border border-neutral-200 rounded p-4"
          data-testid="arithmetic-panel"
        >
          <ArithmeticPanel arithmetic={snap.arithmetic} />
        </div>
      )}

      <div>
        <h2 className="text-sm font-medium mb-2">Blockers</h2>
        <BlockersList blockers={snap.blockers} />
      </div>
    </div>
  );
}
