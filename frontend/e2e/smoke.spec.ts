/**
 * Criterion #8 smoke: login+TOTP → command center → drill workspace →
 * confirm probable → see audit trail.
 *
 * The audit trail assertion is done via API (GET no such public endpoint
 * yet — for the smoke, we shell into the backend and SELECT from
 * audit_log). If we later expose an /audit endpoint, swap the query
 * for an HTTP call.
 */
import { test, expect } from "@playwright/test";
import { authenticator } from "otplib";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { seedFirmAndData, type Seed } from "./seed";


// See seed.ts — Playwright compiles to CJS so we resolve from cwd,
// which is ``frontend/`` when ``npm run test:e2e`` is invoked there.
const REPO_ROOT = resolve(process.cwd(), "..");


function runInBackend(script: string): string {
  const result = spawnSync(
    "docker",
    ["compose", "run", "--rm", "-T", "backend", "python", "-"],
    { input: script, cwd: REPO_ROOT, encoding: "utf-8" }
  );
  if (result.status !== 0) {
    throw new Error(
      `backend python failed (status=${result.status})\n` +
      `stdout=${result.stdout}\nstderr=${result.stderr}`
    );
  }
  return result.stdout;
}


let seed: Seed;


test.beforeAll(async () => {
  seed = await seedFirmAndData();
});


test("full flow: login → command center → workspace → confirm → audit", async ({
  page,
}) => {
  // --- 0. Sanity check: can the API accept a login from Node? If this
  // fails, the browser will certainly fail too and we should surface the
  // real error (CORS misconfig, API down, wrong credentials) instead of
  // a generic "URL didn't change" timeout.
  const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
  const preTotp = authenticator.generate(seed.totpSecret);
  const preLogin = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: seed.email,
      password: seed.password,
      totp_code: preTotp,
    }),
  });
  if (!preLogin.ok) {
    throw new Error(
      `pre-login check failed: ${preLogin.status} ${await preLogin.text()}`
    );
  }

  // Also verify CORS headers surface — the browser fetch will fail
  // silently otherwise.
  const cors = await fetch(`${API}/auth/login`, {
    method: "OPTIONS",
    headers: {
      Origin: "http://localhost:3000",
      "Access-Control-Request-Method": "POST",
      "Access-Control-Request-Headers": "content-type",
    },
  });
  const allow = cors.headers.get("access-control-allow-origin");
  if (!allow) {
    throw new Error(
      `API is missing CORS: OPTIONS /auth/login returned no ` +
      `access-control-allow-origin header. ` +
      `Restart the api service to pick up the CORSMiddleware.`
    );
  }

  // --- 1. Login + TOTP (fresh code, in case the pre-login used up window) ---
  const totpCode = authenticator.generate(seed.totpSecret);
  await page.goto("/login");
  await page.getByTestId("login-email").fill(seed.email);
  await page.getByTestId("login-password").fill(seed.password);
  await page.getByTestId("login-totp").fill(totpCode);
  await page.getByTestId("login-submit").click();

  // Wait for either the URL to change OR an error to appear. If the
  // URL doesn't change within 5s, dump the on-page error text so we
  // know what the frontend actually saw.
  try {
    await expect(page).toHaveURL(/\/command-center/, { timeout: 5_000 });
  } catch (err) {
    const errorText = await page
      .getByTestId("login-error")
      .textContent()
      .catch(() => null);
    throw new Error(
      `Login did not redirect. Frontend error on the page: ` +
      `${JSON.stringify(errorText)}. Original assertion: ${err}`
    );
  }

  // --- 2. Command center row visible + drill link ---
  await page.getByTestId("period-input").fill(seed.period);
  // wait for at least one row to render for our GSTIN
  const row = page.getByTestId("cc-row").first();
  await expect(row).toBeVisible({ timeout: 15_000 });

  // Score column carries either "Not yet scored" or a number — we
  // triggered scoring in the seed, so it should be a number for the
  // GSTR1 row of the seeded gstin.
  const drillLink = page.getByTestId("cc-drill").first();
  await drillLink.click();

  await expect(page).toHaveURL(/\/workspace\//);

  // --- 3. Reconciliation tab: supplier_default rows must render BOTH
  //         states (with near-misses AND without). Neither is a
  //         reachable ungated state (criterion #2).
  await page.getByTestId("tab-reconciliation").click();
  await page.getByTestId("bucket-supplier_default").click();

  // The seed produces two supplier_default rows: SD-A has a same-supplier
  // 2B entry with the same normalized number but a wildly different
  // amount (near-miss). SD-B is from a different supplier (SUP_B) which
  // has no 2B entry at all → empty near-miss list, fallback copy.
  await expect(page.getByTestId("near-miss-list").first()).toBeVisible({
    timeout: 5_000,
  });
  await expect(page.getByTestId("near-miss-empty").first()).toBeVisible();

  // The empty-state copy must warn against assuming supplier default.
  await expect(
    page.getByText(
      /Verify register entry details \(supplier GSTIN, invoice number, period\) before assuming supplier default/,
      { exact: false }
    )
  ).toBeVisible();

  // --- 4. Probable bucket: one row, confirm it, verify it disappears ---
  await page.getByTestId("bucket-probable").click();
  const confirmBtn = page.getByTestId("confirm-match").first();
  await expect(confirmBtn).toBeVisible({ timeout: 5_000 });
  await confirmBtn.click();

  // Success banner from the workspace page's `message` state.
  await expect(page.getByText(/Match confirmed\. Audit row recorded/))
    .toBeVisible({ timeout: 5_000 });
  // Re-fetch fires after confirm — bucket should now be empty.
  await expect(page.getByText(/No rows in this bucket/))
    .toBeVisible({ timeout: 5_000 });

  // --- 5. Returns tab, click score → arithmetic panel ---
  await page.getByTestId("tab-returns").click();
  const score = page.getByTestId("score-value");
  await expect(score).toBeVisible();
  await score.click();
  await expect(page.getByTestId("arithmetic-panel")).toBeVisible();

  // --- 6. Audit trail via backend SQL peek ---
  const auditScript = `
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
with engine.begin() as c:
    rows = c.execute(text(
        "SELECT action FROM audit_log WHERE firm_id = :f ORDER BY at"
    ), {"f": "${seed.firmId}"}).fetchall()
print("|".join(a for (a,) in rows))
`;
  const out = runInBackend(auditScript);
  const actions = out.trim().split(/\r?\n/).pop()!.split("|");
  expect(actions).toContain("client.created");
  expect(actions).toContain("gstin.added");
  expect(actions).toContain("validation.triggered");
  expect(actions).toContain("reconciliation.triggered");
  expect(actions).toContain("score.triggered");
  // The confirm we just did lands as its own audit row.
  expect(actions).toContain("match.confirmed");
});
