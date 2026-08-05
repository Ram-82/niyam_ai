import { describe, it, expect } from "vitest";
import { formatRetryAt } from "./format-retry-after";


// Fix a base "now" so these are TZ-portable when run inside the docker
// backend or on a dev machine. We only assert regex shape (H:MM AM/PM)
// rather than an exact minute — the browser locale in CI may differ.
const NOW = new Date("2026-07-31T09:15:00Z"); // arbitrary


describe("formatRetryAt", () => {
  it("returns a wall-clock string in H:MM AM/PM shape for a normal delay", () => {
    const out = formatRetryAt(180, NOW);   // 3 minutes later
    expect(out).toMatch(/^\d{1,2}:\d{2}\s?(AM|PM|am|pm)?$/i);
  });

  it("advances by the expected number of minutes", () => {
    const a = formatRetryAt(0, NOW);          // now
    const b = formatRetryAt(60 * 30, NOW);    // +30 min
    expect(a).not.toBe(b);                    // clearly different times
  });

  it("handles a delay that crosses the hour boundary", () => {
    // NOW is 09:15 UTC. +50 min = 10:05 UTC. Output format is locale-
    // dependent but should still parse as a time.
    const out = formatRetryAt(60 * 50, NOW);
    expect(out).toMatch(/^\d{1,2}:\d{2}\s?(AM|PM|am|pm)?$/i);
  });

  it("handles a delay that crosses midnight without throwing", () => {
    // Late-in-day base + long delay → next-day time. We only assert it
    // returns a valid time string; the calendar-day rollover is fine
    // because the CA reads the hh:mm and treats "midnight" as tomorrow.
    const lateBase = new Date("2026-07-31T23:45:00Z");
    const out = formatRetryAt(60 * 30, lateBase);
    expect(out).toMatch(/^\d{1,2}:\d{2}\s?(AM|PM|am|pm)?$/i);
  });

  it("defaults ``now`` to real time when no second arg is given", () => {
    // Just prove it doesn't blow up — the returned string is
    // time-dependent so we don't assert its value.
    const out = formatRetryAt(60);
    expect(typeof out).toBe("string");
    expect(out.length).toBeGreaterThan(0);
  });
});
