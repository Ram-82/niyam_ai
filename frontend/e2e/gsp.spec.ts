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
import { authenticator } from "otplib";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
const REPO_ROOT = resolve(process.cwd(), "..");
// The primary fixture GSTIN. app/gsp/fixtures/gstr2b_<gstin>_<period>.json.
const CLIENT_GSTIN = "29ZZZZZ9999Z9Z9";
const MOCK_OTP = "123456";


function runInBackend(script: string): string {
  const r = spawnSync(
    "docker",
    ["compose", "run", "--rm", "-T", "backend", "python", "-"],
    { input: script, cwd: REPO_ROOT, encoding: "utf-8" }
  );
  if (r.status !== 0) {
    throw new Error(
      `runInBackend failed: ${r.status}\n--- stdout ---\n${r.stdout}\n--- stderr ---\n${r.stderr}`
    );
  }
  return r.stdout;
}


type Ctx = {
  firmId: string;
  gstinProfileId: string;
  email: string;
  password: string;
  totpSecret: string;
  token: string;
};


async function seedFirmAndConnect(): Promise<Ctx> {
  const email = `gsp-${randomUUID()}@example.com`;
  const password = "Correct-Horse-Battery-Staple-42";
  const seed = `
import uuid, pyotp
from sqlalchemy import create_engine, text
from app.auth.passwords import hash_password
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = uuid.uuid4()
user_id = uuid.uuid4()
client_id = uuid.uuid4()
gstin_id = uuid.uuid4()
secret = pyotp.random_base32()
with engine.begin() as c:
    c.execute(text("INSERT INTO ca_firm (id, name) VALUES (:i, 'GspCo')"), {"i": firm_id})
    c.execute(text(
        "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
        "totp_secret, totp_confirmed, is_active) VALUES "
        "(:i, :f, :e, :ph, 'admin', :ts, TRUE, TRUE)"),
        {"i": user_id, "f": firm_id, "e": ${JSON.stringify(email)},
         "ph": hash_password(${JSON.stringify(password)}), "ts": secret})
    c.execute(text(
        "INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'Sandbox Client')"),
        {"c": client_id, "f": firm_id})
    c.execute(text(
        "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
        "VALUES (:g, :f, :c, :gstin, '29')"),
        {"g": gstin_id, "f": firm_id, "c": client_id, "gstin": ${JSON.stringify(CLIENT_GSTIN)}})
print(f"{firm_id}|{user_id}|{secret}|{gstin_id}")
`;
  const raw = runInBackend(seed).trim();
  const line = raw.split(/\r?\n/).pop() || "";
  const [firmId, , totpSecret, gstinProfileId] = line.split("|");

  const totpCode = authenticator.generate(totpSecret);
  const loginRes = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, totp_code: totpCode }),
  });
  if (!loginRes.ok) {
    throw new Error(`login failed: ${loginRes.status} ${await loginRes.text()}`);
  }
  const { access_token: token } = await loginRes.json();
  return { firmId, gstinProfileId, email, password, totpSecret, token };
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
