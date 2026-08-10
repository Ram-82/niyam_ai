"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeleton";
import type { RulePackRow, CloneResponse } from "@/lib/types";

const inputCls =
  "border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink focus-visible:border-accent font-mono";
const btnPrimaryCls =
  "px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast disabled:opacity-50";
const btnSecCls =
  "px-3 py-1.5 border border-rule text-sm font-semibold rounded-sm hover:bg-paper-raised transition-colors duration-fast disabled:opacity-50";


export default function RulePackPage() {
  const [packs, setPacks] = useState<RulePackRow[] | null>(null);
  const [editing, setEditing] = useState<{ id: string; json: string } | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function reload() {
    try {
      const rows = await api<RulePackRow[]>("/rule-packs");
      setPacks(rows);
    } catch (e) {
      setMsg({ kind: "error", text: `Load failed — ${e}` });
    }
  }

  useEffect(() => { reload(); }, []);

  const active = packs?.find((p) => p.active);
  const firmPacks = packs?.filter((p) => !p.is_global) ?? [];

  async function handleClone() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api<CloneResponse>("/rule-packs/clone", { method: "POST" });
      setMsg({ kind: "ok", text: `Draft created: ${res.version} — edit it below, then activate.` });
      await reload();
      // Auto-open the editor for the new draft.
      api<{ payload: Record<string, unknown> }>(`/rule-packs/${res.id}`)
        .then((data) => {
          setEditing({ id: res.id, json: JSON.stringify(data.payload, null, 2) });
          setJsonError(null);
        })
        .catch(() => { /* user can click Edit in the draft list */ });
    } catch (e) {
      setMsg({ kind: "error", text: `Clone failed — ${e}` });
    } finally {
      setBusy(false);
    }
  }

  function openEdit(pack: RulePackRow) {
    api<{ payload: Record<string, unknown> }>(`/rule-packs/${pack.id}`)
      .then((data) => {
        setEditing({ id: pack.id, json: JSON.stringify(data.payload, null, 2) });
        setJsonError(null);
      })
      .catch(() => {
        setEditing({ id: pack.id, json: "{}" });
        setJsonError(null);
      });
  }

  async function saveEdit() {
    if (!editing) return;
    setJsonError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(editing.json);
    } catch {
      setJsonError("Invalid JSON — fix the syntax before saving.");
      return;
    }
    setBusy(true);
    try {
      await api(`/rule-packs/${editing.id}`, {
        method: "PATCH",
        body: { payload: parsed },
      });
      setMsg({ kind: "ok", text: "Payload saved." });
      setEditing(null);
      await reload();
    } catch (e) {
      setMsg({ kind: "error", text: `Save failed — ${e}` });
    } finally {
      setBusy(false);
    }
  }

  async function handleActivate(packId: string) {
    setBusy(true);
    setMsg(null);
    try {
      await api(`/rule-packs/${packId}/activate`, { method: "POST" });
      setMsg({ kind: "ok", text: "Pack activated for this firm." });
      await reload();
    } catch (e) {
      setMsg({ kind: "error", text: `Activate failed — ${e}` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Rule pack"
        context="Validation and reconciliation parameters. Firm-specific packs override the global default."
      />

      <nav className="text-xs flex gap-4">
        <a href="/settings" className="text-accent hover:text-accent-hover hover:underline font-semibold">
          ← Firm settings
        </a>
      </nav>

      {msg && (
        <p className={
          "text-sm border rounded-md px-3 py-2 max-w-[720px] " +
          (msg.kind === "ok"
            ? "bg-green-bg text-green-fg border-rule"
            : "bg-red-bg text-red-fg border-rule")
        }>
          {msg.text}
        </p>
      )}

      {/* Active pack summary */}
      <section className="bg-paper-raised border border-rule rounded-md overflow-hidden max-w-[720px]">
        <div className="px-6 py-3 border-b border-rule bg-paper flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Active pack
          </h2>
          {active && (
            <span className={
              "text-xs font-semibold px-2 py-0.5 rounded-sm " +
              (active.is_global
                ? "bg-amber-bg text-amber-fg"
                : "bg-green-bg text-green-fg")
            }>
              {active.is_global ? "global default" : "firm-specific"}
            </span>
          )}
        </div>
        {packs === null && <div className="p-6"><SkeletonTable rows={2} cols={3} /></div>}
        {packs !== null && !active && (
          <div className="p-6 text-sm text-ink-muted">No active rule pack found.</div>
        )}
        {active && (
          <div className="px-6 py-4 space-y-2">
            <div className="flex gap-4 text-sm">
              <span className="text-ink-muted w-24 shrink-0">Version</span>
              <span className="font-mono text-ink">{active.version}</span>
            </div>
            <div className="flex gap-4 text-sm">
              <span className="text-ink-muted w-24 shrink-0">Notes</span>
              <span className="text-ink">{active.notes || "—"}</span>
            </div>
            {active.is_global && (
              <p className="text-xs text-ink-muted pt-2">
                Using the global pack. Clone it to create a firm-specific override.
              </p>
            )}
            <div className="pt-2 flex gap-2">
              {active.is_global && (
                <button
                  className={btnPrimaryCls}
                  onClick={handleClone}
                  disabled={busy}
                >
                  Clone &amp; customize for this firm
                </button>
              )}
              {!active.is_global && (
                <button
                  className={btnSecCls}
                  onClick={() => openEdit(active)}
                  disabled={busy}
                >
                  Edit payload
                </button>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Firm-specific drafts */}
      {firmPacks.filter((p) => !p.active).length > 0 && (
        <section className="bg-paper-raised border border-rule rounded-md overflow-hidden max-w-[720px]">
          <div className="px-6 py-3 border-b border-rule bg-paper">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Draft packs
            </h2>
          </div>
          <ul className="divide-y divide-rule text-sm">
            {firmPacks.filter((p) => !p.active).map((pack) => (
              <li key={pack.id} className="px-6 py-3 flex items-center gap-3">
                <span className="font-mono text-ink flex-1">{pack.version}</span>
                <span className="text-ink-muted text-xs">{pack.notes || "—"}</span>
                <button
                  className={btnSecCls + " text-xs"}
                  onClick={() => openEdit(pack)}
                  disabled={busy}
                >
                  Edit
                </button>
                <button
                  className={btnPrimaryCls + " text-xs"}
                  onClick={() => handleActivate(pack.id)}
                  disabled={busy}
                >
                  Activate
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* JSON editor modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-paper border border-rule rounded-md w-full max-w-3xl shadow-lg flex flex-col max-h-[90vh]">
            <div className="px-6 py-3 border-b border-rule flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink">Edit rule pack payload</h3>
              <button
                className="text-ink-muted hover:text-ink text-xs"
                onClick={() => { setEditing(null); setJsonError(null); }}
              >
                Cancel
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <p className="text-xs text-ink-muted mb-2">
                Edit the JSON payload. Changes apply on the next engine run after activation.
                Do not remove <code className="font-mono">provisional: true</code> from statutory
                values without CA verification.
              </p>
              {jsonError && (
                <p className="text-xs text-red-fg mb-2">{jsonError}</p>
              )}
              <textarea
                className={inputCls + " w-full h-96 resize-y text-xs"}
                value={editing.json}
                onChange={(e) => setEditing({ ...editing, json: e.target.value })}
                spellCheck={false}
              />
            </div>
            <div className="px-6 py-3 border-t border-rule flex gap-2 justify-end">
              <button
                className={btnSecCls}
                onClick={() => { setEditing(null); setJsonError(null); }}
              >
                Cancel
              </button>
              <button
                className={btnPrimaryCls}
                onClick={saveEdit}
                disabled={busy}
              >
                {busy ? "Saving…" : "Save payload"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
