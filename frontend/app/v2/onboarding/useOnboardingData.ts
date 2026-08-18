"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

/* ---------------------------- Backend types ---------------------------- */

export type FirmSettings = {
  name: string;
  plan: string;
  reminders_enabled: boolean;
  narrator_enabled: boolean;
  admin_whatsapp_number: string | null;
};

export type ClientRow = {
  id: string;
  legal_name: string;
  created_at: string;
};

export type UserRow = {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  totp_confirmed: boolean;
  last_login_at: string | null;
};

export type InviteRow = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
};

export type MeRow = {
  id: string;
  email: string;
  firm_id: string;
  firm_name: string;
  role: string;
  totp_confirmed: boolean;
  last_login_at: string | null;
};

export type FirmGspStatus = {
  total_gstins: number;
  connected: number;
  reconnect_needed: number;
  not_connected: number;
  any_connected: boolean;
  summary_label: string;
};

/* ---------------------------- Hook ---------------------------- */

export type OnboardingState = {
  me: MeRow | null;
  firm: FirmSettings | null;
  clients: ClientRow[] | null;
  users: UserRow[] | null;
  invites: InviteRow[] | null;
  gsp: FirmGspStatus | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useOnboardingData(): OnboardingState {
  const [me, setMe] = useState<MeRow | null>(null);
  const [firm, setFirm] = useState<FirmSettings | null>(null);
  const [clients, setClients] = useState<ClientRow[] | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [invites, setInvites] = useState<InviteRow[] | null>(null);
  const [gsp, setGsp] = useState<FirmGspStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([
      api<MeRow>("/auth/me"),
      api<FirmSettings>("/firm/settings"),
      api<ClientRow[]>("/clients"),
      api<UserRow[]>("/users"),
      api<InviteRow[]>("/invites/"),
      api<FirmGspStatus>("/gsp/firm-status"),
    ]).then((results) => {
      if (cancelled) return;
      const [m, f, c, u, i, g] = results;
      setMe(m.status === "fulfilled" ? m.value : null);
      setFirm(f.status === "fulfilled" ? f.value : null);
      setClients(c.status === "fulfilled" ? c.value : null);
      setUsers(u.status === "fulfilled" ? u.value : null);
      setInvites(i.status === "fulfilled" ? i.value : null);
      setGsp(g.status === "fulfilled" ? g.value : null);
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
    me, firm, clients, users, invites, gsp,
    loading, error,
    reload: () => setReloadKey((k) => k + 1),
  };
}

/* ---------------------------- Derivations ---------------------------- */

export type StepStatus = "done" | "active" | "pending";

export type OnboardingStep = {
  n: number;
  title: string;
  sub: string;
  state: StepStatus;
};

/** Derive the 6-step onboarding progression from real firm state.
 *
 * Step-completion heuristics (documented so future edits stay honest):
 *   1. Firm details   — done if firm.name loaded (always true post-registration)
 *   2. Invite team    — done if any non-owner active user OR any pending invite
 *   3. Connect GSP    — currently pending (no firm-wide connection endpoint)
 *   4. Import first   — done if clients.length >= 1
 *   5. AI narrator    — done if firm.narrator_enabled has any explicit value
 *                       (backend defaults to false so this is effectively
 *                       always done — kept as "done" for UI simplicity)
 *   6. Ready          — active once steps 1–5 are all done
 */
export function buildSteps(
  firm: FirmSettings | null,
  clients: ClientRow[] | null,
  users: UserRow[] | null,
  invites: InviteRow[] | null,
  gsp: FirmGspStatus | null,
): OnboardingStep[] {
  const firmDone = firm !== null;
  const activeUsers = users?.filter((u) => u.is_active) ?? [];
  const pendingInvites = invites?.filter(
    (i) => !i.accepted_at && new Date(i.expires_at).getTime() > Date.now(),
  ) ?? [];
  const teamDone = activeUsers.length > 1 || pendingInvites.length > 0;
  const gspDone = gsp?.any_connected ?? false;
  const clientCount = clients?.length ?? 0;
  const importDone = clientCount > 0;
  const narratorDone = firm !== null; // narrator_enabled is always set
  const allDone = firmDone && teamDone && gspDone && importDone && narratorDone;

  const status = (done: boolean, isActive: boolean): StepStatus =>
    done ? "done" : isActive ? "active" : "pending";

  // Active step = first non-done step.
  const chain = [firmDone, teamDone, gspDone, importDone, narratorDone];
  const firstUndone = chain.findIndex((d) => !d);

  return [
    {
      n: 1,
      title: "Firm details",
      sub: firm ? `${firm.name} · ${firm.plan} plan` : "Loading firm profile…",
      state: status(firmDone, firstUndone === 0),
    },
    {
      n: 2,
      title: "Invite your team",
      sub: teamDone
        ? `${activeUsers.length} active teammate${activeUsers.length === 1 ? "" : "s"}${pendingInvites.length ? ` · ${pendingInvites.length} pending invite${pendingInvites.length === 1 ? "" : "s"}` : ""}`
        : "You're the only user. Invite teammates from Settings.",
      state: status(teamDone, firstUndone === 1),
    },
    {
      n: 3,
      title: "Connect your GSP",
      sub: gsp
        ? gsp.summary_label
        : "Per-GSTIN connection — set up from Settings › Data sources",
      state: status(gspDone, firstUndone === 2),
    },
    {
      n: 4,
      title: "Import your first client",
      sub: importDone
        ? `${clientCount} client${clientCount === 1 ? "" : "s"} imported`
        : "Add clients from the Clients screen or via CSV",
      state: status(importDone, firstUndone === 3),
    },
    {
      n: 5,
      title: "AI narrator preference",
      sub: firm
        ? firm.narrator_enabled
          ? "Enabled — GSTR summaries auto-generated on filing"
          : "Off — enable per firm from Settings when ready"
        : "—",
      state: status(narratorDone, firstUndone === 4),
    },
    {
      n: 6,
      title: "You're ready",
      sub: allDone ? "All steps complete — launch your dashboard" : "Finish the steps above to unlock",
      state: allDone ? "active" : "pending",
    },
  ];
}

export function completedCount(steps: OnboardingStep[]): number {
  return steps.filter((s) => s.state === "done").length;
}

export function nameFromEmail(email: string | null | undefined): string {
  if (!email) return "";
  const localPart = email.split("@")[0];
  return localPart
    .split(/[._-]/)
    .map((p) => (p.length > 0 ? p[0].toUpperCase() + p.slice(1) : p))
    .join(" ");
}

export function initialsFrom(text: string): string {
  const words = text.trim().split(/\s+/);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}
