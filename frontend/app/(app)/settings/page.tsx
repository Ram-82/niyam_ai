"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { StubBadge } from "@/components/atoms";
import type { Client, User } from "@/lib/types";


export default function SettingsPage() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [clients, setClients] = useState<Client[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    try {
      const [u, c] = await Promise.all([
        api<User[]>("/users"),
        api<Client[]>("/clients"),
      ]);
      setUsers(u);
      setClients(c);
    } catch (e) {
      setMessage(String(e));
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function createClient(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    await api("/clients", {
      method: "POST",
      body: {
        trade_name: String(form.get("trade_name") || ""),
        language: String(form.get("language") || "en"),
      },
    });
    setMessage("Client created");
    (e.currentTarget as HTMLFormElement).reset();
    refresh();
  }

  async function assign(userId: string, clientId: string) {
    await api("/assignments", {
      method: "POST",
      body: { user_id: userId, client_id: clientId },
    });
    setMessage("Assignment created");
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Firm settings</h1>
      {message && (
        <p className="text-sm bg-green-50 border border-green-200 rounded p-2">
          {message}
        </p>
      )}

      <section>
        <h2 className="text-sm font-medium mb-2">Users</h2>
        <table className="w-full text-sm border border-neutral-200 bg-white">
          <thead className="bg-neutral-50 text-left">
            <tr>
              <th className="p-2">Email</th>
              <th className="p-2">Role</th>
              <th className="p-2">Active</th>
              <th className="p-2">TOTP</th>
              <th className="p-2">Assign to client</th>
            </tr>
          </thead>
          <tbody>
            {(users || []).map((u) => (
              <tr key={u.id}>
                <td className="p-2">{u.email}</td>
                <td className="p-2">{u.role}</td>
                <td className="p-2">{u.is_active ? "yes" : "no"}</td>
                <td className="p-2">{u.totp_confirmed ? "yes" : "no"}</td>
                <td className="p-2">
                  <select
                    onChange={(e) => {
                      if (e.target.value) assign(u.id, e.target.value);
                      e.target.value = "";
                    }}
                    className="border border-neutral-300 rounded text-xs"
                    defaultValue=""
                  >
                    <option value="">Choose client…</option>
                    {(clients || []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.trade_name}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="text-sm font-medium mb-2">Clients</h2>
        <form onSubmit={createClient} className="mb-3 flex items-center gap-2">
          <input
            name="trade_name"
            required
            placeholder="Trade name"
            className="border border-neutral-300 rounded px-2 py-1 text-sm"
          />
          <input
            name="language"
            defaultValue="en"
            className="border border-neutral-300 rounded px-2 py-1 text-sm w-16"
          />
          <button className="px-3 py-1 bg-blue-600 text-white text-sm rounded">
            Create client
          </button>
        </form>
        <ul className="text-sm">
          {(clients || []).map((c) => (
            <li key={c.id} className="py-1 border-b border-neutral-200">
              {c.trade_name}
              <span className="font-mono text-xs text-neutral-500 ml-2">
                {c.id.slice(0, 8)}…
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-sm font-medium mb-2">Deferred to P2</h2>
        <div className="flex flex-wrap gap-2">
          <StubBadge>WhatsApp report delivery</StubBadge>
          <StubBadge>Vernacular 2-pager narration (LLM)</StubBadge>
          <StubBadge>Live GSP pull</StubBadge>
          <StubBadge>OCR invoice capture</StubBadge>
          <StubBadge>Notice assistant</StubBadge>
          <StubBadge>Advisory nudges</StubBadge>
        </div>
      </section>
    </div>
  );
}
