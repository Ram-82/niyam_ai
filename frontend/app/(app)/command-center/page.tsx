"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { defaultPeriod } from "@/lib/constants";
import { ITCCell, ITCHeader, ScoreCell } from "@/components/atoms";
import type { CommandCenterResponse, CommandCenterRow } from "@/lib/types";


export default function CommandCenterPage() {
  const [period, setPeriod] = useState(defaultPeriod());
  const [rows, setRows] = useState<CommandCenterRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    api<CommandCenterResponse>(`/command-center?period=${period}`)
      .then((r) => {
        if (!cancelled) setRows(r.rows);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [period]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-semibold">Command center</h1>
        <label className="ml-auto text-sm">
          Period:{" "}
          <input
            type="text"
            className="border border-neutral-300 rounded px-2 py-0.5 font-mono w-24"
            value={period}
            pattern="[0-9]{6}"
            onChange={(e) => setPeriod(e.target.value)}
            data-testid="period-input"
          />
          <span className="text-xs text-neutral-500 ml-1">YYYYMM</span>
        </label>
      </div>

      {error && (
        <p className="text-sm text-red-700">Error loading rows: {error}</p>
      )}
      {rows === null && !error && (
        <p className="text-sm text-neutral-500">Loading…</p>
      )}

      {rows && (
        <table className="w-full text-sm border border-neutral-200 bg-white">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-2">Client</th>
              <th className="p-2">GSTIN</th>
              <th className="p-2">Return</th>
              <th className="p-2 text-right">Score</th>
              <th className="p-2 text-right">Days to due</th>
              <th className="p-2 text-right">
                <ITCHeader label="ITC at risk" />
              </th>
              <th className="p-2 text-right">Blockers</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={`${r.gstin_profile_id}-${r.return_type}`}
                className={i % 2 ? "bg-neutral-50" : ""}
                data-testid="cc-row"
              >
                <td className="p-2">{r.client_name}</td>
                <td className="p-2 font-mono text-xs">{r.gstin}</td>
                <td className="p-2">{r.return_type}</td>
                <td className="p-2 text-right">
                  <ScoreCell score={r.score} />
                </td>
                <td className="p-2 text-right font-mono">
                  {r.days_to_due_date ?? "—"}
                </td>
                <td className="p-2 text-right">
                  <ITCCell paise={r.itc_at_risk_paise} />
                </td>
                <td className="p-2 text-right">{r.blockers_count}</td>
                <td className="p-2 text-right">
                  <Link
                    href={`/workspace/${r.gstin_profile_id}?period=${r.period}&return_type=${r.return_type}`}
                    className="text-blue-700 hover:underline"
                    data-testid="cc-drill"
                  >
                    Open →
                  </Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="p-4 text-center text-neutral-500">
                  No clients yet. Create one in Settings.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
