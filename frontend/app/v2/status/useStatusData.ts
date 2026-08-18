"use client";

import { useEffect, useState } from "react";

/* Public status page — hits /health + /readyz directly, not through the
 * authenticated api() wrapper. Both endpoints are unauthenticated
 * (Docker/k8s probe them without any credentials). */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/* ---------------------------- Backend types ---------------------------- */

export type HealthResponse = {
  status: string;
  rule_pack_version: string;
};

export type ReadyResponse = {
  status: "ok" | "degraded";
  postgres: string;
  redis: string;
};

/* ---------------------------- Hook ---------------------------- */

export type StatusState = {
  health: HealthResponse | null;
  ready: ReadyResponse | null;
  loading: boolean;
  error: string | null;
  lastFetched: Date | null;
  reload: () => void;
};

async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`/health returned ${res.status}`);
  return res.json();
}

async function fetchReady(): Promise<ReadyResponse> {
  // /readyz returns 503 when degraded but the body still has usable data.
  const res = await fetch(`${API_BASE}/readyz`, { cache: "no-store" });
  if (res.status !== 200 && res.status !== 503) {
    throw new Error(`/readyz returned ${res.status}`);
  }
  return res.json();
}

export function useStatusData(): StatusState {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.allSettled([fetchHealth(), fetchReady()]).then((results) => {
      if (cancelled) return;
      const [h, r] = results;
      setHealth(h.status === "fulfilled" ? h.value : null);
      setReady(r.status === "fulfilled" ? r.value : null);
      const firstErr = results.find((x) => x.status === "rejected") as
        | PromiseRejectedResult
        | undefined;
      if (firstErr) {
        setError(String(firstErr.reason?.message ?? firstErr.reason));
      }
      setLastFetched(new Date());
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reloadKey]);

  return {
    health, ready,
    loading, error, lastFetched,
    reload: () => setReloadKey((k) => k + 1),
  };
}

/* ---------------------------- Derivations ---------------------------- */

export type ServiceState = "operational" | "degraded" | "down" | "unmonitored";

export type ServiceRow = {
  name: string;
  state: ServiceState;
  detail: string;
};

export function overallState(
  health: HealthResponse | null,
  ready: ReadyResponse | null,
  error: string | null,
): ServiceState {
  if (error && !health && !ready) return "down";
  if (ready?.status === "degraded") return "degraded";
  if (health && ready?.status === "ok") return "operational";
  return "unmonitored";
}

export function buildServices(
  health: HealthResponse | null,
  ready: ReadyResponse | null,
): ServiceRow[] {
  const pg: ServiceState =
    !ready ? "unmonitored" : ready.postgres === "ok" ? "operational" : "degraded";
  const rd: ServiceState =
    !ready ? "unmonitored" : ready.redis === "ok" ? "operational" : "degraded";
  const api: ServiceState = health ? "operational" : "unmonitored";
  return [
    {
      name: "Web application (frontend)",
      state: "operational",
      detail: "Rendered — you're seeing this page.",
    },
    {
      name: "API (backend)",
      state: api,
      detail: health
        ? `Rule pack: ${health.rule_pack_version === "unseeded" ? "unseeded (seed script not run)" : `v${health.rule_pack_version}`}`
        : "No response from /health",
    },
    {
      name: "PostgreSQL database",
      state: pg,
      detail: ready ? (ready.postgres === "ok" ? "Reachable via app role" : ready.postgres) : "Unknown — /readyz failed",
    },
    {
      name: "Redis cache & session store",
      state: rd,
      detail: ready ? (ready.redis === "ok" ? "Reachable" : ready.redis) : "Unknown — /readyz failed",
    },
    {
      name: "GSTN Suvidha Provider integration",
      state: "unmonitored",
      detail: "No dedicated healthcheck endpoint. Monitored per-firm via pull attempts.",
    },
    {
      name: "AI narrator (Anthropic + Gemini)",
      state: "unmonitored",
      detail: "No dedicated healthcheck endpoint. Errors surface per narration run.",
    },
    {
      name: "WhatsApp Business API",
      state: "unmonitored",
      detail: "No dedicated healthcheck endpoint. Errors surface per message.",
    },
    {
      name: "Background workers (RQ)",
      state: "unmonitored",
      detail: "No dedicated healthcheck endpoint. Queue depth not exposed.",
    },
  ];
}

export function stateLabel(state: ServiceState): string {
  switch (state) {
    case "operational": return "Operational";
    case "degraded": return "Degraded";
    case "down": return "Down";
    case "unmonitored": return "Not monitored via API";
  }
}

export function stateColorVar(state: ServiceState): { fg: string; bg: string } {
  switch (state) {
    case "operational": return { fg: "var(--success)", bg: "var(--success-soft)" };
    case "degraded": return { fg: "var(--warning)", bg: "var(--warning-soft)" };
    case "down": return { fg: "var(--danger)", bg: "var(--danger-soft)" };
    case "unmonitored": return { fg: "var(--text-muted)", bg: "var(--row-hover)" };
  }
}

export function formatRelativeSeconds(d: Date | null): string {
  if (!d) return "—";
  const diff = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const m = Math.floor(diff / 60);
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)} hr ago`;
}
