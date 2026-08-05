/**
 * /settings/suppliers — CRUD on the firm's supplier directory.
 *
 * The chase-flow prefill lookup goes against the same table (GET
 * /supplier-contacts/by-gstin/{gstin}). This page is where the CA
 * seeds and maintains the directory before/between chase flows.
 *
 * Kept intentionally minimal: table + search + add form + delete.
 * Full edit is a follow-up (PATCH endpoint is already available).
 */
"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { DataTable, type Column } from "@/components/Table";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonTable } from "@/components/Skeleton";
import { PageHeader } from "@/components/PageHeader";
import { formatTimestampIN } from "@/lib/format-date";
import type { SupplierContactRow } from "@/lib/types";


const inputCls =
  "border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm text-ink focus-visible:border-accent";
const btnPrimaryCls =
  "px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover transition-colors duration-fast";
const btnDangerCls =
  "px-2 py-1 text-xs bg-paper border border-rule text-red-fg font-semibold rounded-sm hover:border-red-fg transition-colors duration-fast";


export default function SuppliersPage() {
  const [rows, setRows] = useState<SupplierContactRow[] | null>(null);
  const [q, setQ] = useState("");
  const [message, setMessage] = useState<{
    kind: "ok" | "error";
    text: string;
  } | null>(null);

  async function refresh() {
    try {
      const qParam = q ? `?q=${encodeURIComponent(q)}` : "";
      const list = await api<SupplierContactRow[]>(
        `/supplier-contacts${qParam}`,
      );
      setRows(list);
    } catch (e) {
      setMessage({ kind: "error", text: String(e) });
    }
  }

  useEffect(() => {
    refresh();
    // Deliberately no q dependency — the search input has its own
    // "Search" button so we don't hammer the endpoint on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setMessage(null);
    const body = {
      supplier_gstin: String(form.get("gstin") || "").toUpperCase(),
      name: String(form.get("name") || ""),
      whatsapp_number: String(form.get("whatsapp") || "") || null,
      email: String(form.get("email") || "") || null,
      notes: String(form.get("notes") || "") || null,
    };
    try {
      await api("/supplier-contacts", { method: "POST", body });
      setMessage({ kind: "ok", text: `Added ${body.name}.` });
      (e.currentTarget as HTMLFormElement).reset();
      refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setMessage({
            kind: "error",
            text: "That GSTIN is already in your directory. Delete + re-add if you need to overwrite.",
          });
        } else if (err.status === 400) {
          setMessage({
            kind: "error",
            text: `Rejected: ${err.message}. Check the GSTIN format (15 chars) and E.164 phone (+CountryDigits).`,
          });
        } else {
          setMessage({ kind: "error", text: `${err.message} (HTTP ${err.status})` });
        }
      } else {
        setMessage({ kind: "error", text: String(err) });
      }
    }
  }

  async function remove(row: SupplierContactRow) {
    if (
      !confirm(
        `Delete ${row.name} (${row.supplier_gstin})? This is not reversible.`,
      )
    )
      return;
    try {
      await api(`/supplier-contacts/${row.id}`, { method: "DELETE" });
      setMessage({ kind: "ok", text: `Removed ${row.name}.` });
      refresh();
    } catch (e) {
      setMessage({ kind: "error", text: String(e) });
    }
  }

  const columns: Column<SupplierContactRow>[] = [
    {
      key: "name",
      header: "Supplier",
      cell: (r) => <span className="text-ink font-semibold">{r.name}</span>,
      sortable: true,
      sortValue: (r) => r.name.toLowerCase(),
    },
    {
      key: "gstin",
      header: "GSTIN",
      cell: (r) => <span className="font-mono text-xs">{r.supplier_gstin}</span>,
      sortable: true,
      sortValue: (r) => r.supplier_gstin,
      width: "12rem",
    },
    {
      key: "wa",
      header: "WhatsApp",
      cell: (r) =>
        r.whatsapp_number ? (
          <span className="font-mono text-xs">{r.whatsapp_number}</span>
        ) : (
          <span className="text-ink-muted italic text-xs">—</span>
        ),
      width: "12rem",
    },
    {
      key: "email",
      header: "Email",
      cell: (r) =>
        r.email ? (
          <span className="font-mono text-xs">{r.email}</span>
        ) : (
          <span className="text-ink-muted italic text-xs">—</span>
        ),
    },
    {
      key: "updated",
      header: "Updated",
      cell: (r) => (
        <span className="text-xs font-mono text-ink-muted">
          {formatTimestampIN(r.updated_at)}
        </span>
      ),
      sortable: true,
      sortValue: (r) => r.updated_at,
      width: "12rem",
    },
    {
      key: "action",
      header: "",
      cell: (r) => (
        <button onClick={() => remove(r)} className={btnDangerCls}>
          Delete
        </button>
      ),
      align: "right",
      width: "6rem",
    },
  ];

  return (
    <>
      <PageHeader
        title="Supplier directory"
        context={
          <span>
            Prefills the chase modal. Firm-scoped; not visible to other firms.
          </span>
        }
      />

      {message && (
        <p
          className={
            "text-sm rounded-md px-3 py-2 border border-rule " +
            (message.kind === "ok"
              ? "bg-green-bg text-green-fg"
              : "bg-red-bg text-red-fg")
          }
        >
          {message.text}
        </p>
      )}

      <form
        onSubmit={create}
        className="bg-paper-raised border border-rule rounded-md p-3 grid grid-cols-6 gap-3 text-sm"
      >
        <label className="col-span-2">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold block mb-1">
            Name
          </span>
          <input
            name="name"
            required
            placeholder="Ravi Textiles"
            className={inputCls + " w-full"}
          />
        </label>
        <label>
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold block mb-1">
            GSTIN
          </span>
          <input
            name="gstin"
            required
            minLength={15}
            maxLength={15}
            placeholder="29ABCDE1234F1Z5"
            className={inputCls + " w-full font-mono"}
          />
        </label>
        <label>
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold block mb-1">
            WhatsApp
          </span>
          <input
            name="whatsapp"
            placeholder="+91XXXXXXXXXX"
            className={inputCls + " w-full font-mono"}
          />
        </label>
        <label>
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold block mb-1">
            Email
          </span>
          <input
            name="email"
            type="email"
            placeholder="ravi@example.com"
            className={inputCls + " w-full"}
          />
        </label>
        <div className="flex items-end">
          <button type="submit" className={btnPrimaryCls + " w-full"}>
            Add supplier
          </button>
        </div>
        <label className="col-span-6">
          <span className="text-xs uppercase tracking-wide text-ink-muted font-semibold block mb-1">
            Notes (optional)
          </span>
          <input
            name="notes"
            placeholder="Payment terms, contact person, anything the next chase should reference…"
            className={inputCls + " w-full"}
          />
        </label>
      </form>

      <div className="flex items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") refresh();
          }}
          placeholder="Search by name or GSTIN…"
          className={inputCls + " w-72"}
        />
        <button onClick={refresh} className={btnPrimaryCls}>
          Search
        </button>
      </div>

      {rows === null ? (
        <SkeletonTable rows={5} cols={6} />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          initialSort={{ key: "name", dir: "asc" }}
          emptyState={
            <EmptyState
              title="No supplier contacts yet"
              body={
                q
                  ? `No matches for "${q}". Clear the search or add a new supplier above.`
                  : "Add your first supplier above. Once added, the chase modal on the workspace prefills automatically."
              }
            />
          }
        />
      )}
    </>
  );
}
