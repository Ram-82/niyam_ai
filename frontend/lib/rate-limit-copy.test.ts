import { describe, it, expect } from "vitest";
import { RATE_LIMIT_COPY } from "./constants";


// Shape-lock: the frozen-labels rule says restyle-yes / reword-no.
// If someone edits the strings without updating this test, CI stops them.
// P2.1 Stage D copy, approved verbatim.
describe("RATE_LIMIT_COPY — locked strings", () => {
  it("otp_sms_cooldown reads: 'Next OTP request available at X. Cap is 3 per GSTIN per hour…'", () => {
    expect(RATE_LIMIT_COPY.otp_sms_cooldown("3:47 PM")).toBe(
      "Next OTP request available at 3:47 PM. Cap is 3 per GSTIN per hour to protect the registered mobile."
    );
  });

  it("otp_confirm_lockout reads: 'Five wrong OTPs on this GSTIN. Next attempt available at X…'", () => {
    expect(RATE_LIMIT_COPY.otp_confirm_lockout("3:47 PM")).toBe(
      "Five wrong OTPs on this GSTIN. Next attempt available at 3:47 PM. A fresh OTP can be requested after that."
    );
  });

  it("login_lockout reads: 'Five failed sign-in attempts on this email. Try again at X.'", () => {
    expect(RATE_LIMIT_COPY.login_lockout("3:47 PM")).toBe(
      "Five failed sign-in attempts on this email. Try again at 3:47 PM."
    );
  });

  it("no copy string mentions 'contact support' (nor equivalents)", () => {
    // Anti-drift: rate-limit copy must not push ops as the primary path.
    for (const key of Object.keys(RATE_LIMIT_COPY) as (keyof typeof RATE_LIMIT_COPY)[]) {
      const s = RATE_LIMIT_COPY[key]("3:47 PM").toLowerCase();
      expect(s).not.toMatch(/contact\s+(support|us|ops|admin)/);
      expect(s).not.toMatch(/reach out to/);
      expect(s).not.toMatch(/email us/);
    }
  });
});
