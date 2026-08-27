/**
 * Stage 4 e2e — connect a GSTIN in sandbox mode, enter mock OTP, pull,
 * see the pull surface in the imports list, see call-log increment.
 *
 * Prereqs:
 *   - docker compose up -d postgres redis api gsp-mock
 *   - frontend dev server on :3000
 *   - GSP_MODE=mock in the api container (docker-compose sets this)
 *
 * We hit the mock GSP's fixed OTP (123456). The mock server serves
 * fixtures for the primary GSTIN 29ZZZZZ9999Z9Z9; we seed that GSTIN.
 */
import { test, expect } from "@playwright/test";

import { bootstrapFirm } from "./bootstrap";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
// The primary fixture GSTIN. app/gsp/fixtures/gstr2b_<gstin>_<period>.json.
const CLIENT_GSTIN = "29ZZZZZ9999Z9Z9";
const MOCK_OTP = "123456";


type Ctx = {
  firmId: string;
  gstinProfileId: string;
  email: string;
  password: string;
  totpSecret: string;
  token: string;
};


async function seedFirmAndConnect(): Promise<Ctx> {
  const boot = await bootstrapFirm({
    firmName: "GspCo",
    emailPrefix: "gsp",
    clientTradeName: "Sandbox Client",
    gstin: CLIENT_GSTIN,
  });
  return {
    firmId: boot.firmId,
    gstinProfileId: boot.gstinProfileId,
    email: boot.email,
    password: boot.password,
    totpSecret: boot.totpSecret,
    token: boot.token,
  };
}


let ctx: Ctx;
test.beforeAll(async () => {
  ctx = await seedFirmAndConnect();
});


test("connect → mock OTP → pull → imports list + call log increment", async ({ page }) => {
  // -- 0. Sanity: sandbox mode is on and mock server is reachable.
  const modeRes = await fetch(`${API}/gsp/mode`);
  const mode = await modeRes.json();
  expect(mode.sandbox_mode).toBe(true);

  // -- 1. Prime the browser's localStorage with the JWT before navigating,
  // so the app layout's redirect-if-not-logged-in doesn't fire.
  await page.goto("/");
  await page.evaluate((tok) => {
    localStorage.setItem("niyam.access_token", tok);
  }, ctx.token);

  // -- 2. Workspace page (GSTIN scope).
  await page.goto(
    `/workspace/${ctx.gstinProfileId}?period=202606&return_type=GSTR1&gstin=${CLIENT_GSTIN}`
  );

  // Sandbox banner is visible + non-removable in mock mode.
  await expect(page.getByTestId("sandbox-banner")).toBeVisible();

  // Connections panel loads with state = not_connected.
  const panel = page.getByTestId("connections-panel");
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("conn-state")).toContainText("Not connected");

  // -- 3. Click Connect → OTP form appears.
  await page.getByTestId("connect-btn").click();
  await expect(page.getByTestId("otp-form")).toBeVisible();

  // -- 4. Enter the fixed mock OTP and submit.
  await page.getByLabel("OTP").fill(MOCK_OTP);
  await page.getByTestId("otp-submit").click();

  // -- 5. State chip flips to Connected.
  await expect(page.getByTestId("conn-state")).toContainText(
    "Connected",
    { timeout: 10_000 }
  );

  // -- 6. Baseline call count, then Pull-now (first backfill option), then verify increment.
  const usageBefore = await (
    await fetch(`${API}/gsp/usage`, {
      headers: { Authorization: `Bearer ${ctx.token}` },
    })
  ).json();
  const beforeCalls = usageBefore.total_calls;

  await page.getByTestId("pull-now").click();

  // Wait for the "last synced" text to appear — indicates a successful pull.
  await expect(panel).toContainText("Last synced", { timeout: 15_000 });

  const usageAfter = await (
    await fetch(`${API}/gsp/usage`, {
      headers: { Authorization: `Bearer ${ctx.token}` },
    })
  ).json();
  expect(usageAfter.total_calls).toBeGreaterThan(beforeCalls);

  // -- 7. Imports page shows the pull labeled "Live GSP pull".
  await page.goto("/imports");
  await expect(page.getByTestId("source-gsp").first()).toBeVisible({
    timeout: 5000,
  });

  // -- 8. And a gstn_pull row with source='gsp_api' exists in the DB —
  // proves ingestion reuse.
  const check = runInBackend(`
from sqlalchemy import create_engine, text
e = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
with e.begin() as c:
    n = c.execute(
      text("SELECT COUNT(*) FROM gstn_pull WHERE firm_id=:f AND source='gsp_api'"),
      {"f": "${ctx.firmId}"},
    ).scalar_one()
print(n)
`);
  expect(parseInt(check.trim().split(/\r?\n/).pop() || "0", 10)).toBeGreaterThanOrEqual(1);
});


test("reconnect-needed shows the specific stored cause", async ({ page }) => {
  // Reuse the connected session, then force a vendor-side revocation.
  runInBackend(`
from app.gsp import service
service.mark_session_dead(firm_id="${ctx.firmId}",
                          gstin_profile_id="${ctx.gstinProfileId}",
                          reason="consent_revoked")
print("ok")
`);
  await page.goto("/");
  await page.evaluate((tok) => {
    localStorage.setItem("niyam.access_token", tok);
  }, ctx.token);
  await page.goto(
    `/workspace/${ctx.gstinProfileId}?period=202606&return_type=GSTR1&gstin=${CLIENT_GSTIN}`
  );
  const chip = page.getByTestId("conn-state");
  await expect(chip).toContainText("Reconnect needed");
  // Specific cause must be visible (per Stage 4 truth rule: not generic).
  await expect(page.getByTestId("reconnect-reason")).toContainText(
    /Consent was revoked on the GSTN portal/i
  );
});
