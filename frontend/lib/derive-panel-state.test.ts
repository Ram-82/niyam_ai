import { describe, it, expect } from "vitest";
import { derivePanelState } from "./derive-panel-state";
import type { GspConnectionStatus, LatestGspAttempt } from "./types";


function base(over: Partial<GspConnectionStatus> = {}): GspConnectionStatus {
  return {
    gstin_profile_id: "g",
    gstin: "29AAAAA0000A1ZY",
    state: "connected",
    reason: null,
    session_expires_at: null,
    last_successful_pull_at: null,
    last_pull_period: null,
    sandbox_mode: true,
    monthly_call_count: 0,
    backfill_offer: [],
    latest_attempt: null,
    ...over,
  };
}

function attempt(over: Partial<LatestGspAttempt> = {}): LatestGspAttempt {
  return {
    id: "a1",
    status: "succeeded",
    error_kind: null,
    started_at: "2026-07-31T09:00:00Z",
    finished_at: "2026-07-31T09:00:05Z",
    next_retry_at: null,
    ...over,
  };
}


describe("derivePanelState — session + latest attempt blend", () => {
  it("not_connected when session state is not_connected", () => {
    expect(derivePanelState(base({ state: "not_connected" }))).toBe("not_connected");
  });

  it("reconnect_needed when session state is reconnect_needed", () => {
    expect(
      derivePanelState(base({ state: "reconnect_needed", reason: "consent_revoked" }))
    ).toBe("reconnect_needed");
  });

  it("healthy when connected and no attempts have been made", () => {
    expect(derivePanelState(base({ latest_attempt: null }))).toBe("healthy");
  });

  it("healthy when connected and the latest attempt succeeded", () => {
    expect(
      derivePanelState(base({ latest_attempt: attempt({ status: "succeeded" }) }))
    ).toBe("healthy");
  });

  it("healthy when connected and the latest attempt is running (in-flight)", () => {
    expect(
      derivePanelState(base({ latest_attempt: attempt({ status: "running", finished_at: null }) }))
    ).toBe("healthy");
  });

  it("last_pull_failed when connected and the latest attempt is failed", () => {
    expect(
      derivePanelState(
        base({
          latest_attempt: attempt({
            status: "failed",
            error_kind: "gstn_unavailable",
          }),
        })
      )
    ).toBe("last_pull_failed");
  });

  it("last_pull_failed when connected and the latest attempt is retry_scheduled", () => {
    expect(
      derivePanelState(
        base({
          latest_attempt: attempt({
            status: "retry_scheduled",
            error_kind: "gstn_unavailable",
            next_retry_at: "2026-07-31T09:01:00Z",
          }),
        })
      )
    ).toBe("last_pull_failed");
  });
});
