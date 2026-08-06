"use client";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import type { InviteRow, InviteCreated } from "@/lib/types";


const inputCls =
  "border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink focus-visible:border-accent";
const btnPrimaryCls =
  "px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast";
const btnDangerCls =
  "text-xs text-red-fg hover:underline";


function inviteUrl(token: string): string {
  // Public register page — accepts ?token= from the invite email.
  if (typeof window === "undefined") return `/register?token=${token}`;
  return `${window.location.origin}/register?token=${token}`;
}


function statusOf(row: InviteRow): "accepted" | "expired" | "pending" {
  if (row.accepted_at) return "accepted";
  if (new Date(row.expires_at).getTime() < Date.now()) return "expired";
  return "pending";
}


export default function TeamPage() {
  const [rows, setRows] = useState<InviteRow[] | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [justCreated, setJustCreated] = useState<InviteCreated | null>(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  async function refresh() {
    try {
      const r = await api<InviteRow[]>("/invites/");
      setRows(r);
    } catch (e) {
      setMessage({ kind: "error", text: `Load failed — ${String(e)}` });
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreating(true);
    setMessage(null);
    const form = new FormData(e.currentTarget);
    try {
      const created = await api<InviteCreated>("/invites/", {
        method: "POST",
        body: {
          email: String(form.get("email") || "").trim(),
          role: String(form.get("role") || "staff"),
          ttl_hours: Number(form.get("ttl_hours") || 72),
        },
      });
      setJustCreated(created);
      setCopied(false);
      (e.currentTarget as HTMLFormElement).reset();
      refresh();
    } catch (err) {
      const text = err instanceof ApiError ? err.message : String(err);
      setMessage({ kind: "error", text: `Invite failed — ${text}` });
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(row: InviteRow) {
    try {
      await api(`/invites/${row.id}`, { method: "DELETE" });
      setMessage({ kind: "ok", text: `Revoked invite for ${row.email}.` });
      if (justCreated?.invite_id === row.id) setJustCreated(null);
      refresh();
    } catch (err) {
      setMessage({ kind: "error", text: `Revoke failed — ${String(err)}` });
    }
  }

  async function copyLink() {
    if (!justCreated) return;
    try {
      await navigator.clipboard.writeText(inviteUrl(justCreated.invite_token));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const cols: Column<InviteRow>[] = useMemo(
    () => [
      {
        key: "email",
        header: "Email",
        cell: (r) => r.email,
        sortable: true,
        sortValue: (r) => r.email,
      },
      {
        key: "role",
        header: "Role",
        cell: (r) => (
          <span className="text-xs font-semibold px-2 py-0.5 rounded-sm bg-accent-tint text-accent">
            {r.role}
          </span>
        ),
        width: "6rem",
      },
      {
        key: "status",
        header: "Status",
        cell: (r) => {
          const s = statusOf(r);
          const cls =
            s === "accepted"
              ? "text-green-fg"
              : s === "expired"
              ? "text-ink-muted"
              : "text-amber-fg";
          return <span className={`text-xs font-semibold ${cls}`}>{s}</span>;
        },
        width: "7rem",
      },
      {
        key: "expires_at",
        header: "Expires",
        cell: (r) => new Date(r.expires_at).toLocaleString(),
        sortable: true,
        sortValue: (r) => r.expires_at,
        width: "13rem",
      },
      {
        key: "created_at",
        header: "Invited",
        cell: (r) => new Date(r.created_at).toLocaleString(),
        sortable: true,
        sortValue: (r) => r.created_at,
        width: "13rem",
      },
      {
        key: "actions",
        header: "",
        cell: (r) =>
          statusOf(r) === "pending" ? (
            <button
              type="button"
              onClick={() => onRevoke(r)}
              className={btnDangerCls}
              data-testid={`revoke-${r.email}`}
            >
              Revoke
            </button>
          ) : (
            <span className="text-ink-muted text-xs">—</span>
          ),
        width: "6rem",
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="Team"
        context="Invite staff or fellow admins. Each invite is a one-time link — copy it and send it out of band (email, WhatsApp)."
      />
      <nav className="text-xs flex gap-4">
        <a
          href="/settings"
          className="text-accent hover:text-accent-hover hover:underline font-semibold"
        >
          ← Firm settings
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
        <h2 className="text-sm font-semibold text-ink">Invite someone</h2>
        <form
          onSubmit={onCreate}
          className="bg-paper-raised border border-rule rounded-md p-6 max-w-[720px] flex items-end gap-3 flex-wrap"
        >
          <label className="flex-1 min-w-[16rem]">
            <span className="text-sm font-semibold text-ink">Email</span>
            <input
              name="email"
              required
              type="email"
              placeholder="colleague@example.com"
              className={"mt-1 w-full " + inputCls}
              data-testid="invite-email"
            />
          </label>
          <label className="w-32">
            <span className="text-sm font-semibold text-ink">Role</span>
            <select name="role" defaultValue="staff" className={"mt-1 w-full " + inputCls}>
              <option value="staff">staff</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <label className="w-28">
            <span className="text-sm font-semibold text-ink">Valid (h)</span>
            <input
              name="ttl_hours"
              type="number"
              defaultValue={72}
              min={1}
              max={720}
              className={"mt-1 w-full " + inputCls}
            />
          </label>
          <button
            className={btnPrimaryCls}
            disabled={creating}
            data-testid="invite-submit"
          >
            {creating ? "Creating…" : "Create invite"}
          </button>
        </form>
      </section>

      {justCreated && (
        <section
          className="max-w-[720px] border border-accent bg-accent-tint rounded-md p-4 space-y-2"
          data-testid="invite-just-created"
        >
          <div className="text-sm font-semibold text-ink">Copy this invite link now</div>
          <p className="text-xs text-ink-muted">
            The link is shown once. Once you leave this page it cannot be
            re-displayed — you'd have to revoke and re-invite.
          </p>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={inviteUrl(justCreated.invite_token)}
              className={"flex-1 font-mono text-xs " + inputCls}
              onFocus={(e) => e.currentTarget.select()}
              data-testid="invite-link"
            />
            <button
              type="button"
              onClick={copyLink}
              className={btnPrimaryCls}
              data-testid="invite-copy"
            >
              {copied ? "Copied ✓" : "Copy link"}
            </button>
          </div>
          <div className="text-xs text-ink-muted">
            Expires {new Date(justCreated.expires_at).toLocaleString()}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-ink">Invites</h2>
        {rows === null && <SkeletonTable rows={3} cols={5} />}
        {rows !== null && (
          <DataTable
            columns={cols}
            rows={rows}
            rowKey={(r) => r.id}
            initialSort={{ key: "created_at", dir: "desc" }}
            emptyState={
              <EmptyState
                title="No invites yet"
                body="Use the form above to invite a staff user. They'll get a one-time link they can use to set a password."
              />
            }
          />
        )}
      </section>
    </>
  );
}
