"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

/* ---------------------------- Backend types ---------------------------- */

export type UserRow = {
  id: string;
  email: string;
  role: "admin" | "staff" | string;
  is_active: boolean;
  totp_confirmed: boolean;
  last_login_at: string | null;
};

export type InviteRow = {
  id: string;
  email: string;
  role: "admin" | "staff" | string;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
};

export type FirmSettings = {
  name: string;
  plan: string;
  reminders_enabled: boolean;
  narrator_enabled: boolean;
  admin_whatsapp_number: string | null;
};

/* ---------------------------- Team hook ---------------------------- */

export type SettingsState = {
  users: UserRow[] | null;
  invites: InviteRow[] | null;
  firm: FirmSettings | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useSettingsData(): SettingsState {
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [invites, setInvites] = useState<InviteRow[] | null>(null);
  const [firm, setFirm] = useState<FirmSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      api<UserRow[]>("/users"),
      api<InviteRow[]>("/invites/"),
      api<FirmSettings>("/firm/settings"),
    ]).then((results) => {
      if (cancelled) return;
      const [u, i, f] = results;
      setUsers(u.status === "fulfilled" ? u.value : null);
      setInvites(i.status === "fulfilled" ? i.value : null);
      setFirm(f.status === "fulfilled" ? f.value : null);
      const firstErr = results.find((r) => r.status === "rejected") as
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
    users,
    invites,
    firm,
    loading,
    error,
    reload: useCallback(() => setReloadKey((k) => k + 1), []),
  };
}

/* ---------------------------- Invite mutation ---------------------------- */

export type InviteMutation = {
  running: boolean;
  error: string | null;
  success: string | null;
  send: (email: string, role: "admin" | "staff") => Promise<void>;
  clear: () => void;
};

export function useInviteMutation(onSuccess?: () => void): InviteMutation {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const send = useCallback(
    async (email: string, role: "admin" | "staff") => {
      setRunning(true);
      setError(null);
      setSuccess(null);
      try {
        await api("/invites/", {
          method: "POST",
          body: { email, role, ttl_hours: 72 },
        });
        setSuccess(`Invite sent to ${email}`);
        onSuccess?.();
      } catch (e) {
        setError(
          e instanceof ApiError ? `${e.status}: ${e.message}` : String(e),
        );
      } finally {
        setRunning(false);
      }
    },
    [onSuccess],
  );

  return {
    running,
    error,
    success,
    send,
    clear: useCallback(() => {
      setError(null);
      setSuccess(null);
    }, []),
  };
}

/* ---------------------------- Derivations ---------------------------- */

/** UI-ready row combining active users + pending invites into a single
 *  Members table, mimicking the demo data shape. */
export type MemberRow = {
  key: string;
  name: string;
  initials: string;
  email: string;
  subtitle: string | null;
  role: "Owner" | "Admin" | "Staff" | "Invited";
  scopeMain: string;
  scopeMeta: string;
  lastActive: string;
  mfa: "TOTP" | "Not set" | "—";
  status: { label: string; kind: "active" | "pending" | "inactive" | "invited" };
  isOwner: boolean;
};

export function buildMemberRows(
  users: UserRow[] | null,
  invites: InviteRow[] | null,
): MemberRow[] {
  const out: MemberRow[] = [];
  // Users first (owner heuristic: earliest-created admin. Since we
  // don't have created_at on UserRow, treat the first admin returned
  // by the ORDER BY email query as owner — good-enough for display).
  let ownerAssigned = false;
  if (users) {
    for (const u of users) {
      const isAdmin = u.role === "admin";
      const isOwner = isAdmin && !ownerAssigned;
      if (isOwner) ownerAssigned = true;
      out.push({
        key: `u:${u.id}`,
        name: nameFromEmail(u.email),
        initials: initialsFrom(nameFromEmail(u.email)),
        email: u.email,
        subtitle: null,
        role: isOwner ? "Owner" : isAdmin ? "Admin" : "Staff",
        scopeMain: isAdmin ? "All clients" : "Assigned clients",
        scopeMeta: isAdmin ? "unrestricted" : "per client_assignment",
        lastActive: relativeShort(u.last_login_at),
        mfa: u.totp_confirmed ? "TOTP" : "Not set",
        status: u.is_active
          ? u.totp_confirmed
            ? { label: "Active", kind: "active" }
            : { label: "Setup pending", kind: "pending" }
          : { label: "Inactive", kind: "inactive" },
        isOwner,
      });
    }
  }
  // Pending invites (unaccepted, not expired).
  if (invites) {
    const now = Date.now();
    for (const inv of invites) {
      if (inv.accepted_at) continue;
      const expired = new Date(inv.expires_at).getTime() < now;
      if (expired) continue;
      out.push({
        key: `i:${inv.id}`,
        name: inv.email,
        initials: initialsFrom(nameFromEmail(inv.email)),
        email: inv.email,
        subtitle: "invited teammate",
        role: "Invited",
        scopeMain: inv.role === "admin" ? "All clients" : "Assigned clients",
        scopeMeta: `role: ${inv.role}`,
        lastActive: "—",
        mfa: "—",
        status: { label: `Invited · expires ${relativeShort(inv.expires_at)}`, kind: "invited" },
        isOwner: false,
      });
    }
  }
  return out;
}

export function seatsSummary(
  users: UserRow[] | null,
  invites: InviteRow[] | null,
): { used: number; pending: number; label: string } {
  const used = users?.filter((u) => u.is_active).length ?? 0;
  const pending = invites?.filter((i) => !i.accepted_at && new Date(i.expires_at).getTime() > Date.now()).length ?? 0;
  return {
    used,
    pending,
    label: pending > 0 ? `${used} active · ${pending} invited` : `${used} active`,
  };
}

/* ---------------------------- Formatters ---------------------------- */

function nameFromEmail(email: string): string {
  const localPart = email.split("@")[0];
  return localPart
    .split(/[._-]/)
    .map((p) => (p.length > 0 ? p[0].toUpperCase() + p.slice(1) : p))
    .join(" ");
}

function initialsFrom(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

function relativeShort(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 0) {
    // Future date — used for invite expiries.
    const s = Math.abs(diffSec);
    if (s < 3600) return `in ${Math.floor(s / 60)}m`;
    if (s < 86400) return `in ${Math.floor(s / 3600)}h`;
    return `in ${Math.floor(s / 86400)}d`;
  }
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  return `${Math.floor(h / 24)}d ago`;
}
