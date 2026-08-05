import type { GspConnectionStatus } from "./types";


/** UI-facing panel state (P2.1 Stage E). Backend returns session-only
 * state; this pure function blends it with ``latest_attempt`` to
 * produce four buckets. Kept out of the panel component so vitest can
 * import it in a Node environment. */
export type PanelState =
  | "not_connected"
  | "reconnect_needed"
  | "last_pull_failed"
  | "healthy";


/** Single source of the state blend. Pure — testable without React. */
export function derivePanelState(status: GspConnectionStatus): PanelState {
  if (status.state === "not_connected") return "not_connected";
  if (status.state === "reconnect_needed") return "reconnect_needed";
  // status.state === "connected" from here.
  const a = status.latest_attempt;
  if (a && (a.status === "failed" || a.status === "retry_scheduled")) {
    return "last_pull_failed";
  }
  return "healthy";
}
