"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatApiError } from "@/lib/format-api-error";

/* ---------------------------- Backend types ---------------------------- */

export type OcrListRow = {
  id: string;
  gstin_profile_id: string;
  direction: "purchase" | "sale";
  status: "draft" | "accepted" | "rejected";
  adapter: string;
  source_filename: string;
  source_bytes_size: number;
  overall_confidence: number;
  created_at: string;
};

export type OcrField = { value: string | null; confidence: number };

export type OcrDetail = {
  id: string;
  firm_id: string;
  gstin_profile_id: string;
  direction: "purchase" | "sale";
  status: "draft" | "accepted" | "rejected";
  created_at: string;
  adapter: string;
  adapter_version: string;
  source_filename: string;
  source_content_hash: string;
  source_bytes_size: number;
  low_confidence_threshold: number;
  warnings: string[];
  overall_confidence: number;
  supplier_gstin: OcrField;
  invoice_number: OcrField;
  invoice_date: OcrField;
  taxable_value_paise: OcrField;
  cgst_paise: OcrField;
  sgst_paise: OcrField;
  igst_paise: OcrField;
  total_paise: OcrField;
  hsn_sac: OcrField;
};

export type FirmSettings = {
  name: string;
  plan: string;
};

/* ---------------------------- Hook ---------------------------- */

export type ContractsState = {
  rows: OcrListRow[] | null;
  firm: FirmSettings | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useContractsData(): ContractsState {
  const [rows, setRows] = useState<OcrListRow[] | null>(null);
  const [firm, setFirm] = useState<FirmSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      api<OcrListRow[]>("/ocr/extractions?limit=100"),
      api<FirmSettings>("/firm/settings"),
    ]).then((results) => {
      if (cancelled) return;
      const [r, f] = results;
      setRows(r.status === "fulfilled" ? r.value : null);
      setFirm(f.status === "fulfilled" ? f.value : null);
      const firstErr = results.find((x) => x.status === "rejected") as
        | PromiseRejectedResult
        | undefined;
      if (firstErr) {
        const reason = firstErr.reason;
        setError(
          reason instanceof ApiError
            ? `${reason.status}: ${reason.message}`
            : String(reason?.message ?? reason),
        );
      }
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  return {
    rows, firm,
    loading, error,
    reload: () => setReloadKey((k) => k + 1),
  };
}

export function useOcrDetail(id: string | null): {
  detail: OcrDetail | null;
  loading: boolean;
  error: string | null;
} {
  const [detail, setDetail] = useState<OcrDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) { setDetail(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api<OcrDetail>(`/ocr/extractions/${id}`)
      .then((r) => { if (!cancelled) setDetail(r); })
      .catch((e) => {
        if (cancelled) return;
        setError(formatApiError(e));
        setDetail(null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  return { detail, loading, error };
}

/* ---------------------------- Derivations ---------------------------- */

/** OCR extractions treated as "issues" for the contracts panel.
 *  Semantic mapping (documented gap — contract analysis isn't shipped):
 *    - "high" severity   = confidence < 0.70   → needs manual review
 *    - "medium" severity = 0.70 ≤ conf < 0.90  → verify sensitive fields
 *    - "low" severity    = conf ≥ 0.90         → trust the extraction
 */
export type Sev = "high" | "medium" | "low";

export function severityFor(confidence: number): Sev {
  if (confidence < 0.7) return "high";
  if (confidence < 0.9) return "medium";
  return "low";
}

export type StatusCounts = { high: number; medium: number; low: number; total: number };

export function severityCounts(rows: OcrListRow[] | null): StatusCounts {
  const c: StatusCounts = { high: 0, medium: 0, low: 0, total: 0 };
  if (!rows) return c;
  for (const r of rows) {
    c[severityFor(r.overall_confidence)]++;
    c.total++;
  }
  return c;
}

export function statusCounts(rows: OcrListRow[] | null): {
  draft: number; accepted: number; rejected: number;
} {
  const c = { draft: 0, accepted: 0, rejected: 0 };
  if (!rows) return c;
  for (const r of rows) c[r.status]++;
  return c;
}

/** Filter rows by free-text query on filename/adapter/direction. */
export function filterRows(rows: OcrListRow[] | null, q: string): OcrListRow[] {
  if (!rows) return [];
  const query = q.trim().toLowerCase();
  if (!query) return rows;
  return rows.filter((r) =>
    r.source_filename.toLowerCase().includes(query) ||
    r.adapter.toLowerCase().includes(query) ||
    r.direction.toLowerCase().includes(query)
  );
}

/* ---------------------------- Formatters ---------------------------- */

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const day = d.getUTCDate();
  const abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${day} ${abbr[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`;
}

export function formatPaise(paise: string | null): string {
  if (paise == null) return "—";
  const n = Number(paise);
  if (Number.isNaN(n)) return paise;
  return `₹${(n / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function prettyDirection(d: string): string {
  if (d === "purchase") return "Purchase";
  if (d === "sale") return "Sale";
  return d;
}

export function prettyStatus(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
