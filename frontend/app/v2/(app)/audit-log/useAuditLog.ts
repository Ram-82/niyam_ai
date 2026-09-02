"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";

/* ---------------------------- Backend types ---------------------------- */

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

/* ---------------------------- Filter state ---------------------------- */

export type AuditFilters = {
  entity_type: string;
  action_prefix: string;
  since: string; // ISO date (yyyy-mm-dd) or ""
  until: string; // ISO date (yyyy-mm-dd) or ""
};

export const EMPTY_FILTERS: AuditFilters = {
  entity_type: "",
  action_prefix: "",
  since: "",
  until: "",
};

/** Backend endpoint accepts these entity types via audit_log rows. Not
 *  exhaustive but covers everything we currently write. */
export const ENTITY_TYPES = [
  "filing_run",
  "gstin_profile",
  "client",
  "ca_firm",
  "app_user",
  "invite",
  "gsp_session",
  "narrator_call",
  "invoice",
  "ocr_extraction",
] as const;

/** Common action prefixes surfaced as quick-select chips. */
export const ACTION_PREFIXES = [
  "filing.",
  "auth.",
  "client.",
  "gsp.",
  "user.",
  "invite.",
  "narrator.",
] as const;

const PAGE_SIZE = 100;

function buildQuery(filters: AuditFilters, until: string | null): string {
  const params = new URLSearchParams();
  params.set("limit", String(PAGE_SIZE));
  if (filters.entity_type) params.set("entity_type", filters.entity_type);
  if (filters.action_prefix) params.set("action_prefix", filters.action_prefix);
  if (filters.since) params.set("since", `${filters.since}T00:00:00Z`);
  // Load-more cursor beats the user's `until` filter — always the more
  // restrictive of the two.
  const effectiveUntil = until ?? (filters.until ? `${filters.until}T23:59:59Z` : null);
  if (effectiveUntil) params.set("until", effectiveUntil);
  return params.toString();
}

/* ---------------------------- Hook ---------------------------- */

export type AuditLogState = {
  rows: AuditRow[];
  filters: AuditFilters;
  loading: boolean;      // true only for the first page
  loadingMore: boolean;  // true during subsequent load-more calls
  error: string | null;
  hasMore: boolean;
  setFilters: (next: AuditFilters) => void;
  reload: () => void;
  loadMore: () => void;
};

export function useAuditLog(): AuditLogState {
  const [filters, setFiltersState] = useState<AuditFilters>(EMPTY_FILTERS);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const activeRef = useRef(0);

  // Initial + filter-change fetch.
  useEffect(() => {
    const token = ++activeRef.current;
    setLoading(true);
    setError(null);
    api<AuditRow[]>(`/audit-log?${buildQuery(filters, null)}`)
      .then((data) => {
        if (activeRef.current !== token) return;
        setRows(data);
        setHasMore(data.length >= PAGE_SIZE);
      })
      .catch((e: unknown) => {
        if (activeRef.current !== token) return;
        setError(formatApiError(e));
        setRows([]);
        setHasMore(false);
      })
      .finally(() => {
        if (activeRef.current !== token) return;
        setLoading(false);
      });
  }, [filters, reloadKey]);

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore || rows.length === 0) return;
    const cursor = rows[rows.length - 1].at;
    // Server orders DESC by `at`; asking for older rows means until < cursor.
    // Use the cursor value directly — duplicates on the boundary are
    // deduped below.
    setLoadingMore(true);
    setError(null);
    api<AuditRow[]>(`/audit-log?${buildQuery(filters, cursor)}`)
      .then((data) => {
        setRows((prev) => {
          const seen = new Set(prev.map((r) => r.id));
          return [...prev, ...data.filter((r) => !seen.has(r.id))];
        });
        setHasMore(data.length >= PAGE_SIZE);
      })
      .catch((e: unknown) => {
        setError(formatApiError(e));
      })
      .finally(() => setLoadingMore(false));
  }, [filters, rows, hasMore, loadingMore]);

  const setFilters = useCallback((next: AuditFilters) => {
    setFiltersState(next);
  }, []);

  return useMemo(
    () => ({
      rows,
      filters,
      loading,
      loadingMore,
      error,
      hasMore,
      setFilters,
      reload: () => setReloadKey((k) => k + 1),
      loadMore,
    }),
    [rows, filters, loading, loadingMore, error, hasMore, setFilters, loadMore],
  );
}

/* ---------------------------- Formatters ---------------------------- */

/** `filing.marked_filed` → `Filing marked filed`. */
export function humanizeAction(action: string): string {
  const parts = action.replace(".", " ").replace(/_/g, " ").split(/\s+/);
  if (parts.length === 0) return action;
  return parts[0][0].toUpperCase() + parts[0].slice(1) + (parts.length > 1 ? " " + parts.slice(1).join(" ") : "");
}

/** `filing_run` → `Filing run`. */
export function humanizeEntityType(et: string): string {
  return et.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

const RTF = typeof Intl !== "undefined" ? new Intl.RelativeTimeFormat("en", { numeric: "auto" }) : null;

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.round((then - now) / 1000);
  const abs = Math.abs(diffSec);
  if (!RTF) return new Date(iso).toLocaleString();
  if (abs < 60) return RTF.format(diffSec, "second");
  if (abs < 3600) return RTF.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return RTF.format(Math.round(diffSec / 3600), "hour");
  if (abs < 86400 * 30) return RTF.format(Math.round(diffSec / 86400), "day");
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatAbsolute(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

/** Tone token derived from action prefix. Matches the palette used by
 *  the dashboard's ActivityCard. */
export function toneFor(action: string): "success" | "danger" | "warning" | "neutral" {
  if (action.startsWith("filing.filed") || action.startsWith("filing.marked_filed")) return "success";
  if (action.startsWith("auth.lockout") || action.endsWith(".failed") || action.endsWith(".revoked")) return "danger";
  if (action.startsWith("auth.")) return "warning";
  return "neutral";
}
