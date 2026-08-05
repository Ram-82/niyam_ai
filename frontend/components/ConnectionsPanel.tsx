"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type {
  GspConnectionStatus,
  GspPullAttempt,
  LatestGspAttempt,
} from "@/lib/types";
import {
  FAILED_PULL_REASON,
  FAILED_PULL_REASON_DEFAULT,
  GSP_OTP_DELIVERY_COPY,
  GSP_RECONNECT_REASON,
  RATE_LIMIT_COPY,
} from "@/lib/constants";
import { formatPeriod, formatTimestampIN } from "@/lib/format-date";
import { formatIsoAsLocalTime, formatRetryAt } from "@/lib/format-retry-after";
import { derivePanelState, type PanelState } from "@/lib/derive-panel-state";


/**
 * Client-workspace panel: one connection per GSTIN.
 *
 * Four panel states (see ``derivePanelState``):
 *
 *   not_connected      → "Connect" button + one-liner about OTP flow
 *   healthy            → green chip + Last synced + Pull-now + Disconnect
 *                        + optional Backfill offer
 *   last_pull_failed   → amber chip + reason line from FAILED_PULL_REASON
 *                        + Pull-now + Disconnect (no new remediation CTAs)
 *   reconnect_needed   → red chip + SPECIFIC stored cause + Reconnect
 *
 * Never rely on frontend state for sandbox_mode — the layout banner
 * comes from the backend /gsp/mode probe.
 */
export function ConnectionsPanel({ gstinProfileId }: { gstinProfileId: string }) {
  const [status, setStatus] = useState<GspConnectionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [otpFlow, setOtpFlow] = useState<{
    inflight_id: string;
    expires_at: string;
  } | null>(null);
  const [otp, setOtp] = useState("");

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const s = await api<GspConnectionStatus>(
        `/gsp/connection/${gstinProfileId}`
      );
      setStatus(s);
    } catch (e) {
      setError(String(e));
    }
  }, [gstinProfileId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ inflight_id: string; expires_at: string }>(
        "/gsp/consent",
        { method: "POST", body: { gstin_profile_id: gstinProfileId } }
      );
      setOtpFlow(r);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        // 429 already_sent: per-GSTIN SMS-flood cooldown. Wall-clock time
        // is preferred over "a few minutes" — CAs know when to try again.
        const at =
          e.retryAfterSeconds != null
            ? formatRetryAt(e.retryAfterSeconds)
            : "a later time";
        setError(RATE_LIMIT_COPY.otp_sms_cooldown(at));
      } else {
        setError(String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitOtp(e: React.FormEvent) {
    e.preventDefault();
    if (!otpFlow) return;
    setBusy(true);
    setError(null);
    try {
      await api("/gsp/consent/confirm", {
        method: "POST",
        body: { inflight_id: otpFlow.inflight_id, otp },
      });
      setOtpFlow(null);
      setOtp("");
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        setError(
          e.body && typeof e.body === "object" && (e.body as any).detail === "otp_invalid"
            ? "OTP didn't match — ask the client to read it again."
            : "OTP expired. Request a new one."
        );
      } else if (e instanceof ApiError && e.status === 429) {
        // 429 otp_locked: per-(user, gstin) OTP brute-force lockout.
        const at =
          e.retryAfterSeconds != null
            ? formatRetryAt(e.retryAfterSeconds)
            : "a later time";
        setError(RATE_LIMIT_COPY.otp_confirm_lockout(at));
      } else {
        setError(String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function pullNow(period: string) {
    setBusy(true);
    setError(null);
    try {
      await api("/gsp/pull", {
        method: "POST",
        body: { gstin_profile_id: gstinProfileId, period },
      });
      await refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError("Reconnect required — session is no longer live.");
        await refresh();
      } else {
        setError(String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!confirm("Disconnect this GSTIN from Niyam? A reconnect will need a fresh OTP.")) {
      return;
    }
    setBusy(true);
    try {
      await api("/gsp/disconnect", {
        method: "POST",
        body: { gstin_profile_id: gstinProfileId },
      });
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!status) {
    return (
      <section
        className="border border-rule rounded-md p-4 bg-paper-raised text-sm text-ink-muted"
        data-testid="connections-panel-loading"
      >
        Loading connection status…
      </section>
    );
  }

  const panelState = derivePanelState(status);

  return (
    <section
      className="border border-rule rounded-md p-4 bg-paper-raised space-y-3"
      data-testid="connections-panel"
    >
      <header className="flex items-center gap-3">
        <h3 className="text-sm font-semibold text-ink">GSP connection</h3>
        <StateChip panelState={panelState} reason={status.reason} />
        <span className="ml-auto text-xs text-ink-muted font-mono">
          {status.monthly_call_count} calls this month
        </span>
      </header>

      {panelState === "healthy" && (
        <div className="text-sm text-ink-muted">
          {status.last_successful_pull_at ? (
            <>
              Last synced {formatTimestampIN(status.last_successful_pull_at)}
              {" · "}
              period {formatPeriod(status.last_pull_period)}
            </>
          ) : (
            <>Connected. No pulls yet.</>
          )}
        </div>
      )}

      {panelState === "last_pull_failed" && status.latest_attempt && (
        <LastPullFailedBanner attempt={status.latest_attempt} />
      )}

      {panelState === "reconnect_needed" && (
        <p
          className="text-sm bg-red-bg text-red-fg border border-rule rounded-sm px-3 py-2"
          data-testid="reconnect-reason"
        >
          {GSP_RECONNECT_REASON[status.reason || ""] ||
            "Session is no longer usable — reconnect."}
        </p>
      )}

      {otpFlow && (
        <form
          onSubmit={submitOtp}
          className="border border-rule rounded-sm p-3 space-y-2 bg-paper"
          data-testid="otp-form"
        >
          <p className="text-xs text-ink-muted">{GSP_OTP_DELIVERY_COPY}</p>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="off"
            pattern="\d{4,8}"
            required
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            placeholder="Enter OTP from client"
            className="border border-rule bg-paper-raised rounded-sm px-2 py-1 text-sm font-mono w-32"
            aria-label="OTP"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover disabled:opacity-50"
              data-testid="otp-submit"
            >
              Confirm connection
            </button>
            <button
              type="button"
              onClick={() => { setOtpFlow(null); setOtp(""); }}
              className="px-3 py-1.5 text-sm text-ink-muted hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="flex gap-2 flex-wrap">
        {panelState === "not_connected" && (
          <button
            onClick={connect}
            disabled={busy || !!otpFlow}
            className="px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover disabled:opacity-50"
            data-testid="connect-btn"
          >
            Connect this GSTIN
          </button>
        )}
        {panelState === "reconnect_needed" && (
          <button
            onClick={connect}
            disabled={busy || !!otpFlow}
            className="px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover disabled:opacity-50"
            data-testid="reconnect-btn"
          >
            Reconnect
          </button>
        )}
        {(panelState === "healthy" || panelState === "last_pull_failed") && (
          <>
            <button
              onClick={() =>
                pullNow(
                  status.backfill_offer[0]?.period ||
                    status.last_pull_period ||
                    defaultPullPeriod()
                )
              }
              disabled={busy}
              className="px-3 py-1.5 bg-accent text-paper-raised text-sm font-semibold rounded-sm hover:bg-accent-hover disabled:opacity-50"
              data-testid="pull-now"
            >
              Pull latest 2B
            </button>
            <button
              onClick={disconnect}
              disabled={busy}
              className="px-3 py-1.5 border border-rule text-sm text-ink hover:bg-grey-bg rounded-sm disabled:opacity-50"
              data-testid="disconnect-btn"
            >
              Disconnect
            </button>
          </>
        )}
      </div>

      {(panelState === "healthy" || panelState === "last_pull_failed") &&
        status.backfill_offer.length > 0 && (
        <div
          className="border border-rule rounded-sm p-3 bg-paper space-y-2"
          data-testid="backfill-offer"
        >
          <p className="text-xs text-ink-muted">
            Backfill: no data yet for these already-generated periods.
            Each button runs a Pull-now.
          </p>
          <div className="flex gap-2 flex-wrap">
            {status.backfill_offer.map((b) => (
              <button
                key={b.period}
                onClick={() => pullNow(b.period)}
                disabled={busy}
                className="px-2 py-1 border border-rule text-xs text-ink hover:bg-grey-bg rounded-sm font-mono disabled:opacity-50"
              >
                Backfill {b.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <p
          className="text-sm bg-red-bg text-red-fg border border-rule rounded-sm px-3 py-2"
          data-testid="conn-error"
        >
          {error}
        </p>
      )}

      <FailedPullSurface gstinProfileId={gstinProfileId} />
    </section>
  );
}


function StateChip({
  panelState,
  reason,
}: {
  panelState: PanelState;
  reason: string | null;
}) {
  const cls =
    panelState === "healthy"
      ? "bg-green-bg text-green-fg"
      : panelState === "last_pull_failed"
      ? "bg-amber-100 text-amber-900"
      : panelState === "reconnect_needed"
      ? "bg-red-bg text-red-fg"
      : "bg-grey-bg text-ink-muted";
  const label =
    panelState === "healthy"
      ? "Connected"
      : panelState === "last_pull_failed"
      ? "Connected · last pull failed"
      : panelState === "reconnect_needed"
      ? `Reconnect needed (${reason || "unknown"})`
      : "Not connected";
  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-sm ${cls}`}
      data-testid="conn-state"
    >
      {label}
    </span>
  );
}


/**
 * Amber banner rendered when panelState === "last_pull_failed". Reason
 * copy is looked up from FAILED_PULL_REASON in ONE place, keyed by
 * ``latest_attempt.error_kind`` (unknown → conservative default).
 */
function LastPullFailedBanner({ attempt }: { attempt: LatestGspAttempt }) {
  const kind = attempt.error_kind || "unknown";
  const entry = FAILED_PULL_REASON[kind] || FAILED_PULL_REASON_DEFAULT;
  const nextAt = formatIsoAsLocalTime(attempt.next_retry_at);
  const text = entry.text({ next_retry_at: nextAt });
  return (
    <p
      className="text-sm bg-amber-100 text-amber-900 border border-amber-300 rounded-sm px-3 py-2"
      data-testid="last-pull-failed-reason"
    >
      {text}
    </p>
  );
}


/**
 * Loud, impossible-to-miss surface for failed pulls. Backed by
 * gsp_pull_attempt so a scheduled failure is not silent.
 */
function FailedPullSurface({ gstinProfileId }: { gstinProfileId: string }) {
  const [failed, setFailed] = useState<GspPullAttempt[] | null>(null);
  useEffect(() => {
    api<GspPullAttempt[]>(
      `/gsp/pull-attempts?gstin_profile_id=${gstinProfileId}&only_failed=true&limit=5`
    )
      .then(setFailed)
      .catch(() => setFailed([]));
  }, [gstinProfileId]);

  if (!failed || failed.length === 0) return null;
  return (
    <div
      className="border border-red-fg/40 bg-red-bg rounded-sm p-3 space-y-1"
      data-testid="failed-pulls"
    >
      <p className="text-sm font-semibold text-red-fg">
        {failed.length} failed pull{failed.length > 1 ? "s" : ""} — action needed
      </p>
      <ul className="text-xs text-red-fg space-y-0.5">
        {failed.map((f) => (
          <li key={f.id} className="font-mono">
            {formatPeriod(f.period)} · {f.source} · {f.error_kind} · {f.error_message}
          </li>
        ))}
      </ul>
    </div>
  );
}


function defaultPullPeriod(): string {
  const d = new Date();
  const first = new Date(d.getFullYear(), d.getMonth(), 1);
  const prev = new Date(first.getTime() - 86400_000);
  return `${prev.getFullYear()}${String(prev.getMonth() + 1).padStart(2, "0")}`;
}
