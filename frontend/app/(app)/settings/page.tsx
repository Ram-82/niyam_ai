"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { StubBadge } from "@/components/atoms";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import type { Client, User } from "@/lib/types";


const inputCls =
  "border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink focus-visible:border-accent";
const btnPrimaryCls =
  "px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast";


export default function SettingsPage() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [clients, setClients] = useState<Client[] | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function refresh() {
    try {
      const [u, c] = await Promise.all([
        api<User[]>("/users"),
        api<Client[]>("/clients"),
      ]);
      setUsers(u);
      setClients(c);
    } catch (e) {
      setMessage({ kind: "error", text: String(e) });
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function createClient(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await api("/clients", {
        method: "POST",
        body: {
          trade_name: String(form.get("trade_name") || ""),
          language: String(form.get("language") || "en"),
        },
      });
      setMessage({ kind: "ok", text: "Client created." });
      (e.currentTarget as HTMLFormElement).reset();
      refresh();
    } catch (err) {
      setMessage({ kind: "error", text: `Create failed — ${err}. Check the trade name and try again.` });
    }
  }

  async function assign(userId: string, clientId: string) {
    try {
      await api("/assignments", {
        method: "POST",
        body: { user_id: userId, client_id: clientId },
      });
      setMessage({ kind: "ok", text: "Assignment created." });
    } catch (err) {
      setMessage({ kind: "error", text: `Assign failed — ${err}.` });
    }
  }

  const userCols: Column<User>[] = [
    {
      key: "email",
      header: "Email",
      cell: (u) => u.email,
      sortable: true,
      sortValue: (u) => u.email,
    },
    {
      key: "role",
      header: "Role",
      cell: (u) => (
        <span className="text-xs font-semibold px-2 py-0.5 rounded-sm bg-accent-tint text-accent">
          {u.role}
        </span>
      ),
      width: "6rem",
    },
    {
      key: "active",
      header: "Active",
      cell: (u) => (u.is_active ? "Yes" : <span className="text-ink-muted">No</span>),
      width: "5rem",
    },
    {
      key: "totp",
      header: "TOTP",
      cell: (u) =>
        u.totp_confirmed ? (
          <span className="text-green-fg font-semibold">Enrolled</span>
        ) : (
          <span className="text-amber-fg font-semibold">Not enrolled</span>
        ),
      width: "9rem",
    },
    {
      key: "assign",
      header: "Assign to client",
      cell: (u) => (
        <select
          onChange={(e) => {
            if (e.target.value) assign(u.id, e.target.value);
            e.target.value = "";
          }}
          className={inputCls}
          defaultValue=""
        >
          <option value="">Choose client…</option>
          {(clients || []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.trade_name}
            </option>
          ))}
        </select>
      ),
      width: "13rem",
    },
  ];

  return (
    <>
      <PageHeader
        title="Firm settings"
        context="Manage staff, client assignments, and firm preferences."
      />
      <nav className="text-xs flex gap-4">
        <a
          href="/settings/suppliers"
          className="text-accent hover:text-accent-hover hover:underline font-semibold"
        >
          Supplier directory →
        </a>
      </nav>
      {message && (
        <p
          className={
            "text-sm border rounded-md px-3 py-2 max-w-[560px] " +
            (message.kind === "ok"
              ? "bg-green-bg text-green-fg border-rule"
              : "bg-red-bg text-red-fg border-rule")
          }
        >
          {message.text}
        </p>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-ink">Users</h2>
        {users === null && <SkeletonTable rows={3} cols={5} />}
        {users !== null && (
          <DataTable
            columns={userCols}
            rows={users}
            rowKey={(u) => u.id}
            emptyState={
              <EmptyState
                title="No staff users yet"
                body="Only the firm admin exists so far. Invite staff members via POST /invites (dashboard invite flow ships in the next iteration)."
              />
            }
          />
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-ink">Clients</h2>
        <form onSubmit={createClient} className="bg-paper-raised border border-rule rounded-md p-6 max-w-[560px] flex items-end gap-3 flex-wrap">
          <label className="flex-1 min-w-[16rem]">
            <span className="text-sm font-semibold text-ink">Trade name</span>
            <input
              name="trade_name"
              required
              placeholder="e.g. Ramesh Textiles Pvt Ltd"
              className={"mt-1 w-full " + inputCls}
            />
          </label>
          <label className="w-20">
            <span className="text-sm font-semibold text-ink">Lang</span>
            <input
              name="language"
              defaultValue="en"
              className={"mt-1 w-full " + inputCls}
              aria-label="Language code"
            />
          </label>
          <button className={btnPrimaryCls}>Create client</button>
        </form>
        {clients === null && <SkeletonTable rows={3} cols={2} />}
        {clients !== null && clients.length === 0 && (
          <EmptyState
            title="No clients yet"
            body="Add your first client using the form above. Each client can hold multiple GSTINs."
          />
        )}
        {clients !== null && clients.length > 0 && (
          <ul className="text-sm bg-paper-raised border border-rule rounded-md divide-y divide-rule">
            {clients.map((c) => (
              <li key={c.id} className="p-3 flex items-center gap-3">
                <span className="text-ink">{c.trade_name}</span>
                <span className="font-mono text-xs text-ink-muted ml-auto">
                  {c.id.slice(0, 8)}…
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-ink">Live in P2 (sandbox / stubbed)</h2>
        <div className="flex flex-wrap gap-2 text-xs">
          <span
            className="px-2 py-0.5 rounded-sm bg-amber-100 text-amber-900 border border-amber-300 font-semibold"
            title="Live GSP pull is wired end-to-end against a local mock GSP. When a real GSP vendor is provisioned, only app/gsp/adapter_*.py needs a new file."
          >
            Live GSP pull — mock adapter
          </span>
          <StubBadge>WhatsApp report delivery</StubBadge>
          <StubBadge>Vernacular 2-pager narration (LLM)</StubBadge>
          <StubBadge>OCR invoice capture</StubBadge>
          <StubBadge>Notice assistant</StubBadge>
          <StubBadge>Advisory nudges</StubBadge>
        </div>
      </section>
    </>
  );
}
