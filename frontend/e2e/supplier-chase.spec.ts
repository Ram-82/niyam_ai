/**
 * Supplier chase e2e — seed a supplier_default match_result → workspace
 * reconciliation tab → mark near-misses reviewed → open chase modal →
 * approve+send → verify delivery_attempt row.
 *
 * Prereqs mirror whatsapp.spec.ts:
 *   - docker compose up -d postgres redis api
 *   - frontend dev server on :3000
 *   - WHATSAPP_ENABLED=1 in the api container for the send assertions.
 *     If the flag is off, the panel renders the "disabled" callout and
 *     the send assertions are skipped, so the test is safe to run
 *     against a stock docker-compose setup.
 */
import { test, expect } from "@playwright/test";
import { authenticator } from "otplib";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
const REPO_ROOT = resolve(process.cwd(), "..");


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
  runId: string;
  matchId: string;
  email: string;
  password: string;
  totpSecret: string;
  token: string;
};


async function seedFirmWithSupplierDefault(): Promise<Ctx> {
  const email = `chase-${randomUUID()}@example.com`;
  const password = "Correct-Horse-Battery-Staple-42";
  const seed = `
import json, uuid, pyotp
from sqlalchemy import create_engine, text
from app.auth.passwords import hash_password
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = uuid.uuid4()
user_id = uuid.uuid4()
client_id = uuid.uuid4()
gstin_id = uuid.uuid4()
pull_id = uuid.uuid4()
run_id = uuid.uuid4()
match_id = uuid.uuid4()
invoice_id = uuid.uuid4()
secret = pyotp.random_base32()
with engine.begin() as c:
    c.execute(text("INSERT INTO ca_firm (id, name) VALUES (:i, 'ChaseCo')"), {"i": firm_id})
    c.execute(text(
        "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
        "totp_secret, totp_confirmed, is_active) VALUES "
        "(:i, :f, :e, :ph, 'admin', :ts, TRUE, TRUE)"),
        {"i": user_id, "f": firm_id, "e": ${JSON.stringify(email)},
         "ph": hash_password(${JSON.stringify(password)}), "ts": secret})
    c.execute(text(
        "INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'Chase Traders')"),
        {"c": client_id, "f": firm_id})
    c.execute(text(
        "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
        "VALUES (:g, :f, :c, '29ABCDE1234F1Z5', '29')"),
        {"g": gstin_id, "f": firm_id, "c": client_id})
    # Invoice for the match_result to reference.
    c.execute(text(
        "INSERT INTO invoice (id, firm_id, gstin_profile_id, source, direction, "
        "invoice_number, invoice_date, counterparty_gstin, "
        "taxable_value_paise, total_paise, content_hash) VALUES "
        "(:i, :f, :g, 'csv_import', 'purchase', 'CH-1', DATE '2026-06-15', "
        "'29BBBBB1234C2ZZ', 100000, 118000, :h)"),
        {"i": invoice_id, "f": firm_id, "g": gstin_id, "h": f"h-{invoice_id}"})
    c.execute(text(
        "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, return_type, period, "
        "raw_payload, source) VALUES (:pid, :f, :g, 'GSTR2B', '202606', "
        "CAST('{}' AS JSONB), 'json_import')"),
        {"pid": pull_id, "f": firm_id, "g": gstin_id})
    c.execute(text(
        "INSERT INTO reconciliation_run (id, firm_id, gstin_profile_id, period, "
        "rule_pack_version, gstn_pull_id, summary, status) VALUES "
        "(:id, :f, :g, '202606', '1.0.0', :pid, CAST('{}' AS JSONB), 'completed')"),
        {"id": run_id, "f": firm_id, "g": gstin_id, "pid": pull_id})
    c.execute(text(
        "INSERT INTO match_result (id, firm_id, run_id, invoice_id, "
        "bucket, confidence, rule_pack_version, context) VALUES "
        "(:m, :f, :r, :i, 'supplier_default', 0.0, '1.0.0', "
        "CAST(:ctx AS JSONB))"),
        {"m": match_id, "f": firm_id, "r": run_id, "i": invoice_id,
         "ctx": json.dumps({"near_misses": []})})
print(f"{firm_id}|{user_id}|{secret}|{gstin_id}|{run_id}|{match_id}")
`;
  const raw = runInBackend(seed).trim();
  const line = raw.split(/\r?\n/).pop() || "";
  const [firmId, , totpSecret, gstinProfileId, runId, matchId] = line.split("|");

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
  return {
    firmId,
    gstinProfileId,
    runId,
    matchId,
    email,
    password,
    totpSecret,
    token,
  };
}


async function whatsappEnabled(token: string): Promise<boolean> {
  const res = await fetch(`${API}/whatsapp/attempts`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.status !== 503;
}


let ctx: Ctx;
test.beforeAll(async () => {
  ctx = await seedFirmWithSupplierDefault();
});


test("supplier_default row: mark reviewed → send chase → attempt appears", async ({
  page,
}) => {
  const flagOn = await whatsappEnabled(ctx.token);

  await page.goto("/");
  await page.evaluate((tok) => {
    localStorage.setItem("niyam.access_token", tok);
  }, ctx.token);
  // Land straight on the reconciliation tab.
  await page.goto(
    `/workspace/${ctx.gstinProfileId}?period=202606&return_type=GSTR1&gstin=29ABCDE1234F1Z5&tab=reconciliation`,
  );

  // supplier_default bucket is the default selection in ReconciliationTab.
  const panel = page.getByTestId(`chase-panel-${ctx.matchId}`);
  await expect(panel).toBeVisible({ timeout: 10_000 });

  // Backend gate: send button must NOT be visible until "Mark reviewed"
  // has been clicked.
  await expect(page.getByTestId("send-chase")).toHaveCount(0);

  // 1. Mark near-misses reviewed.
  await page.getByTestId("mark-near-miss-reviewed").click();
  // The button hides once reviewedAt is set; the send-chase CTA appears.
  await expect(page.getByTestId("send-chase")).toBeVisible({ timeout: 5_000 });

  if (!flagOn) {
    // With whatsapp disabled the chase modal will 503 on open — the
    // panel renders the disabled callout instead of proceeding.
    test.skip(true, "WHATSAPP_ENABLED off — send assertions skipped");
    return;
  }

  // 2. Open chase modal.
  await page.getByTestId("send-chase").click();
  await expect(page.getByTestId("chase-modal")).toBeVisible();

  // 3. Fill + submit.
  await page.getByTestId("chase-whatsapp-number").fill("+919876543210");
  await page.getByTestId("approve-and-send-chase").click();

  // 4. Attempt row appears (mock transport is synchronous → status='sent').
  await expect(page.getByTestId("delivery-status-sent")).toBeVisible({
    timeout: 10_000,
  });
});
