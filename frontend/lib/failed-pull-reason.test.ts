import { describe, it, expect } from "vitest";
import { FAILED_PULL_REASON, FAILED_PULL_REASON_DEFAULT } from "./constants";


// Shape-lock. Restyle allowed, reword forbidden without touching this test.
// If someone edits a copy string, CI stops them until the test is updated
// deliberately. That is the honest-labels rule applied to error copy.
describe("FAILED_PULL_REASON — locked strings + action flags", () => {
  it("gstn_unavailable is transient/auto-retry with the exact copy", () => {
    const e = FAILED_PULL_REASON["gstn_unavailable"];
    expect(e.needs_action).toBe(false);
    expect(e.text({ next_retry_at: null })).toBe(
      "GSTN was unavailable on the last attempt. Niyam will retry automatically."
    );
    expect(e.text({ next_retry_at: "3:47 PM" })).toBe(
      "GSTN was unavailable on the last attempt. Niyam will retry automatically at 3:47 PM."
    );
  });

  it("rate_limited is transient/auto-retry with the exact copy", () => {
    const e = FAILED_PULL_REASON["rate_limited"];
    expect(e.needs_action).toBe(false);
    expect(e.text({ next_retry_at: null })).toBe(
      "GSP rate limit hit on the last attempt. Niyam will retry automatically."
    );
    expect(e.text({ next_retry_at: "3:47 PM" })).toBe(
      "GSP rate limit hit on the last attempt. Niyam will retry automatically at 3:47 PM."
    );
  });

  it("session_expired needs reconnect, no auto-retry", () => {
    const e = FAILED_PULL_REASON["session_expired"];
    expect(e.needs_action).toBe(true);
    expect(e.text({})).toBe(
      "The GSP session had expired at the time of the last attempt."
    );
  });

  it("consent_revoked needs reconnect", () => {
    const e = FAILED_PULL_REASON["consent_revoked"];
    expect(e.needs_action).toBe(true);
    expect(e.text({})).toBe(
      "Consent was revoked on the GSTN portal; the last attempt could not proceed."
    );
  });

  it("session_dead needs reconnect", () => {
    const e = FAILED_PULL_REASON["session_dead"];
    expect(e.needs_action).toBe(true);
    expect(e.text({})).toBe(
      "No live GSP session at the time of the last attempt."
    );
  });

  it("unknown is conservative (no speculation about cause)", () => {
    const e = FAILED_PULL_REASON["unknown"];
    expect(e.needs_action).toBe(true);
    expect(e.text({})).toBe(
      "The last attempt failed with an unclassified error. Try Pull-now again; if it repeats, reconnect."
    );
  });

  it("default fallback === the unknown mapping", () => {
    expect(FAILED_PULL_REASON_DEFAULT).toBe(FAILED_PULL_REASON["unknown"]);
  });

  it("no copy mentions 'contact support' (nor blame words)", () => {
    for (const [_kind, entry] of Object.entries(FAILED_PULL_REASON)) {
      const s = entry.text({ next_retry_at: null }).toLowerCase();
      expect(s).not.toMatch(/contact\s+(support|us|ops|admin)/);
      expect(s).not.toMatch(/reach out to/);
      expect(s).not.toMatch(/your fault|you failed|you did/);
    }
  });
});
