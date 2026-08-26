"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

/* ---------------------------- Types ---------------------------- */

export type FilingListRow = {
  id: string;
  gstin_profile_id: string;
  gstin: string;
  client_id: string;
  client_name: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  status: "draft" | "approved" | "filed";
  updated_at: string;
};

export type FilingRow = {
  id: string;
  gstin_profile_id: string;
  return_type: "GSTR1" | "GSTR3B";
  period: string;
  status: "draft" | "approved" | "filed";
  rule_pack_version: string;
  generated_by: string | null;
  created_at: string;
  updated_at: string;
  payload: FilingPayload | null;
};

export type FilingPayload = {
  gstin?: string;
  ret_period?: string;
  sup_details?: {
    osup_det?: MoneyBlock;
    osup_zero?: MoneyBlock;
    osup_nil_exmp?: { txval: number };
    isup_rev?: MoneyBlock;
    osup_nongst?: { txval: number };
  };
  itc_elg?: {
    itc_avl?: Array<{ ty: string } & MoneyBlock>;
    itc_rev?: Array<{ ty: string } & MoneyBlock>;
    itc_net?: MoneyBlock;
    itc_inelg?: Array<{ ty: string } & MoneyBlock>;
  };
  tx_pmt?: {
    tx_pd_cash?: MoneyBlock;
    tx_pd_itc?: MoneyBlock;
  };
  _meta?: {
    rule_pack_version?: string;
    return_type?: string;
    period?: string;
    sections_covered?: string[];
    sections_deferred?: string[];
  };
};

export type MoneyBlock = {
  txval?: number;
  iamt?: number;
  camt?: number;
  samt?: number;
  csamt?: number;
};

export type ReadinessBlocker = {
  code: string;
  owner: "ca" | "client" | string;
  severity?: "error" | "warning" | string;
  message?: string;
  entity_type?: string;
  entity_id?: string;
};

export type ReadinessSnapshot = {
  snapshot_id: string | null;
  return_type: string;
  period: string;
  score: number | null;
  blockers: ReadinessBlocker[];
  arithmetic: Record<string, unknown>;
  rule_pack_version: string | null;
  computed_at: string | null;
};

export type AuditRow = {
  id: string;
  firm_id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  diff: Record<string, unknown>;
  at: string;
  user_email: string | null;
};

/* ---------------------------- Picker hook ---------------------------- */

export type PickerState = {
  filings: FilingListRow[] | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useFilingList(
  filter: { status?: FilingListRow["status"]; limit?: number } = {},
): PickerState {
  const [filings, setFilings] = useState<FilingListRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const { status, limit = 50 } = filter;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    qs.set("limit", String(limit));
    api<FilingListRow[]>(`/filings?${qs.toString()}`)
      .then((rows) => {
        if (!cancelled) setFilings(rows);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
        setFilings(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, limit, reloadKey]);

  return { filings, loading, error, reload: () => setReloadKey((k) => k + 1) };
}

/* ---------------------------- Detail hook ---------------------------- */

export type DetailData = {
  filing: FilingRow | null;
  readiness: ReadinessSnapshot | null;
  activity: AuditRow[] | null;
};

export type DetailState = {
  data: DetailData;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useFilingDetail(filingId: string | null): DetailState {
  const [data, setData] = useState<DetailData>({
    filing: null,
    readiness: null,
    activity: null,
  });
  const [loading, setLoading] = useState<boolean>(!!filingId);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!filingId) {
      setLoading(false);
      setData({ filing: null, readiness: null, activity: null });
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    // Load the filing first — we need its gstin_profile_id + period +
    // return_type to fetch the matching readiness snapshot in parallel
    // with the activity feed.
    (async () => {
      try {
        const filing = await api<FilingRow>(`/filings/${filingId}`);
        if (cancelled) return;
        const [readinessRes, activityRes] = await Promise.allSettled([
          api<ReadinessSnapshot>(
            `/gstins/${filing.gstin_profile_id}/readiness?period=${filing.period}&return_type=${filing.return_type}`,
          ),
          api<AuditRow[]>(
            `/audit-log?entity_type=filing_run&entity_id=${filingId}&limit=50`,
          ),
        ]);
        if (cancelled) return;
        setData({
          filing,
          readiness:
            readinessRes.status === "fulfilled" ? readinessRes.value : null,
          activity: activityRes.status === "fulfilled" ? activityRes.value : [],
        });
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError ? `${e.status}: ${e.message}` : String(e),
        );
        setData({ filing: null, readiness: null, activity: null });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [filingId, reloadKey]);

  return {
    data,
    loading,
    error,
    reload: useCallback(() => setReloadKey((k) => k + 1), []),
  };
}

/* ---------------------------- Mutations ---------------------------- */

export type MutationState = {
  running: boolean;
  error: string | null;
};

export function useFilingMutations(
  filingId: string | null,
  onSuccess?: () => void,
) {
  const [state, setState] = useState<MutationState>({
    running: false,
    error: null,
  });

  const run = useCallback(
    async (path: string, body?: unknown) => {
      if (!filingId) return;
      setState({ running: true, error: null });
      try {
        await api<FilingRow>(path, { method: "POST", body });
        setState({ running: false, error: null });
        onSuccess?.();
      } catch (e) {
        setState({
          running: false,
          error:
            e instanceof ApiError ? `${e.status}: ${e.message}` : String(e),
        });
      }
    },
    [filingId, onSuccess],
  );

  return {
    ...state,
    approve: () => run(`/filings/${filingId}/approve`),
    markFiled: (arn?: string) =>
      run(`/filings/${filingId}/mark-filed`, arn ? { arn } : {}),
    unlock: () => run(`/filings/${filingId}/unlock`),
  };
}

/* ---------------------------- Derivations ---------------------------- */

export function formatRupees(amount: number | undefined | null): string {
  if (amount == null) return "—";
  return `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function formatPeriod(period: string): string {
  if (!/^[0-9]{6}$/.test(period)) return period;
  const year = period.slice(0, 4);
  const month = parseInt(period.slice(4), 10);
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month - 1] ?? "";
  return `${abbr} ${year}`;
}

export function prettyReturnType(rt: string): string {
  if (rt === "GSTR1") return "GSTR-1";
  if (rt === "GSTR3B") return "GSTR-3B";
  return rt;
}

export function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(1, Math.floor((now - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  return `${Math.floor(h / 24)}d ago`;
}

/** Compute the visual workflow-step index (0-5) from filing.status +
 *  readiness signal. Steps: 0 ingest · 1 validation · 2 recon · 3
 *  computation · 4 CA review · 5 file. */
export function workflowStep(
  filing: FilingRow | null,
  readiness: ReadinessSnapshot | null,
): { activeIndex: number; percent: number } {
  if (!filing) return { activeIndex: 0, percent: 0 };
  if (filing.status === "filed") return { activeIndex: 5, percent: 100 };
  if (filing.status === "approved") return { activeIndex: 5, percent: 92 };
  // Draft: check whether blockers remain. If none → CA review step ready,
  // else validation/recon is still in progress conceptually.
  if (readiness && readiness.blockers.length === 0) {
    return { activeIndex: 4, percent: 82 };
  }
  return { activeIndex: 4, percent: 66 };
}
