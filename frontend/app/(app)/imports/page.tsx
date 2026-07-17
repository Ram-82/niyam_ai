"use client";
import { useEffect, useState } from "react";
import { api, apiFormData } from "@/lib/api";
import { StubBadge } from "@/components/atoms";


type ImportJob = {
  id: string;
  kind: string;
  status: string;
  filename: string;
  period: string | null;
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  error_message: string | null;
};


export default function ImportsPage() {
  const [jobs, setJobs] = useState<ImportJob[] | null>(null);
  const [gid, setGid] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    const rows = await api<ImportJob[]>("/imports");
    setJobs(rows);
  }
  useEffect(() => {
    refresh();
  }, []);

  async function uploadInvoices(
    e: React.FormEvent<HTMLFormElement>,
    direction: "purchase" | "sale"
  ) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    form.set("direction", direction);
    if (gid) form.set("gstin_profile_id", gid);
    await apiFormData("/imports/invoices", form);
    setMessage(`${direction} upload queued`);
    refresh();
  }

  async function upload2b(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (gid) form.set("gstin_profile_id", gid);
    await apiFormData("/imports/gstr2b", form);
    setMessage("2B upload queued");
    refresh();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Imports</h1>

      <div className="bg-white border border-neutral-200 rounded p-4 space-y-4">
        <label className="block">
          <span className="text-sm font-medium">GSTIN profile ID</span>
          <input
            className="mt-1 block w-full max-w-md border border-neutral-300 rounded px-2 py-1 font-mono text-sm"
            value={gid}
            onChange={(e) => setGid(e.target.value)}
            placeholder="uuid"
          />
        </label>

        <form
          className="flex items-center gap-2"
          onSubmit={(e) => uploadInvoices(e, "purchase")}
        >
          <input type="file" name="file" required />
          <button className="px-3 py-1 bg-blue-600 text-white text-sm rounded">
            Upload purchase register (CSV/XLSX)
          </button>
        </form>

        <form
          className="flex items-center gap-2"
          onSubmit={(e) => uploadInvoices(e, "sale")}
        >
          <input type="file" name="file" required />
          <button className="px-3 py-1 bg-blue-600 text-white text-sm rounded">
            Upload sales register (CSV/XLSX)
          </button>
        </form>

        <form className="flex items-center gap-2" onSubmit={upload2b}>
          <input type="file" name="file" required accept=".json,application/json" />
          <input
            type="text"
            name="period"
            required
            pattern="[0-9]{6}"
            placeholder="Period YYYYMM"
            className="border border-neutral-300 rounded px-2 py-1 font-mono text-sm w-32"
          />
          <button className="px-3 py-1 bg-blue-600 text-white text-sm rounded">
            Upload GSTR-2B JSON
          </button>
          <StubBadge>Live GSP pull</StubBadge>
        </form>
      </div>

      {message && <p className="text-sm text-green-700">{message}</p>}

      <div>
        <h2 className="text-sm font-medium mb-2">Recent jobs</h2>
        <table className="w-full text-sm border border-neutral-200 bg-white">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-2">Filename</th>
              <th className="p-2">Kind</th>
              <th className="p-2">Period</th>
              <th className="p-2">Status</th>
              <th className="p-2 text-right">Rows (accepted / rejected / dup)</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {(jobs || []).map((j) => (
              <tr key={j.id}>
                <td className="p-2 font-mono text-xs">{j.filename}</td>
                <td className="p-2">{j.kind}</td>
                <td className="p-2 font-mono">{j.period || "—"}</td>
                <td className="p-2">{j.status}</td>
                <td className="p-2 text-right font-mono">
                  {j.accepted_rows} / {j.rejected_rows} / {j.duplicate_rows}
                </td>
                <td className="p-2 text-right">
                  {j.rejected_rows > 0 && (
                    <a
                      href={`${process.env.NIYAM_API_BASE || "http://localhost:8000"}/imports/${j.id}/errors.csv`}
                      className="text-blue-700 hover:underline text-xs"
                    >
                      Download errors.csv
                    </a>
                  )}
                </td>
              </tr>
            ))}
            {jobs && jobs.length === 0 && (
              <tr>
                <td colSpan={6} className="p-4 text-center text-neutral-500">
                  No imports yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
