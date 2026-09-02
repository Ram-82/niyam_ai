"use client";

import { useCallback, useState } from "react";
import { getAccessToken } from "@/lib/auth";
import { formatApiError } from "@/lib/format-api-error";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/* ---------------------------- Backend types ---------------------------- */

export type ImportRowError = { row: number; message: string };

export type ImportResponse = {
  total_rows: number;
  column_headers: string[];
  resolved_mapping: Record<string, string>;
  preview: Record<string, string>[];
  errors: ImportRowError[];
  warnings: ImportRowError[];
  created_clients: number;
  created_gstins: number;
  dry_run: boolean;
};

/* ---------------------------- Hook ---------------------------- */

export type CsvImportState = {
  file: File | null;
  result: ImportResponse | null;
  loading: boolean;
  error: string | null;
  /** true when a commit succeeded — used to gate the "Continue" CTA. */
  committed: boolean;
  pickFile: (f: File) => Promise<void>;
  updateMapping: (m: Record<string, string>) => Promise<void>;
  commit: () => Promise<void>;
  reset: () => void;
};

async function callImport(
  file: File,
  mapping: Record<string, string>,
  dryRun: boolean,
): Promise<ImportResponse> {
  const token = getAccessToken();
  if (!token) throw new Error("Not signed in. Reload and sign in again.");
  const form = new FormData();
  form.append("file", file);
  form.append("mapping", JSON.stringify(mapping));
  const res = await fetch(
    `${API_BASE}/clients/import?dry_run=${dryRun ? "true" : "false"}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    },
  );
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail ?? `Import failed (${res.status})`);
  }
  return body as ImportResponse;
}

export function useCsvImport(onCommit?: () => void): CsvImportState {
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState(false);

  const pickFile = useCallback(async (f: File) => {
    setFile(f);
    setMapping({});
    setResult(null);
    setCommitted(false);
    setLoading(true);
    setError(null);
    try {
      const r = await callImport(f, {}, true);
      setResult(r);
      setMapping(r.resolved_mapping);
    } catch (e: unknown) {
      setError(formatApiError(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateMapping = useCallback(async (m: Record<string, string>) => {
    if (!file) return;
    setMapping(m);
    setLoading(true);
    setError(null);
    try {
      const r = await callImport(file, m, true);
      setResult(r);
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [file]);

  const commit = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const r = await callImport(file, mapping, false);
      setResult(r);
      setCommitted(true);
      onCommit?.();
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [file, mapping, onCommit]);

  const reset = useCallback(() => {
    setFile(null);
    setMapping({});
    setResult(null);
    setError(null);
    setCommitted(false);
  }, []);

  return { file, result, loading, error, committed, pickFile, updateMapping, commit, reset };
}

/* ---------------------------- Field catalogue ---------------------------- */

/** Fields the CSV can map to. Order matters — this is the dropdown order.
 *  Matches backend IMPORT_FIELDS. */
export const IMPORT_FIELDS: { value: string; label: string; required?: boolean }[] = [
  { value: "trade_name", label: "Client name", required: true },
  { value: "gstin", label: "GSTIN" },
  { value: "state_code", label: "State code (2-digit)" },
  { value: "scheme", label: "Scheme (regular / composition)" },
  { value: "language", label: "Language (en / hi / …)" },
  { value: "whatsapp_number", label: "WhatsApp number (E.164)" },
];
