#!/usr/bin/env node
// Filing-cycle walkthrough executor.
//
// The readiness bar: a CA provisioned by the vendor completes one client,
// one GSTIN, one period, from an empty database to a filing marked filed,
// entirely in the browser.
//
// Preparation (outside the browser):
//   1. Build the frontend for production and serve it with `next start`.
//      The instrument does NOT drive the Turbopack dev server — dev-mode
//      compile-on-demand, hot reload, and dev-only error handling are not
//      what a CA would use, and a transient dev compile wedge has already
//      produced a blank workspace that read as a product gap.
//   2. TRUNCATE ca_firm CASCADE so the DB matches the empty-DB starting bar.
//   3. Invoke the documented bootstrap CLI (`python -m app.cli.provision_firm`)
//      to create firm + first admin + legal acceptance + audit_log row.
//      This is vendor onboarding per the readiness bar.
//
// Walkthrough (browser-only from here): sign in, create client, add GSTIN,
// reach the workspace, connect GSP, pull 2B, upload the purchase register,
// reconcile, then generate → approve → mark filed.
//
// ─── Rules this executor obeys ───
//
// R1. A step reports `ok` only when the thing it names actually happened.
//     Absence of a crash is not evidence of success. Every navigation is
//     checked for a real document, a Next.js error overlay, an uncaught
//     exception, and frontend build errors in the container log.
//
// R2. No step carries a pre-authored conclusion. Status and cause are
//     derived at runtime from what was observed. When a step fails and the
//     evidence does not identify why, it reports `cause not established`
//     and attaches the evidence. A plausible invented cause is worse than
//     an admitted gap — a pre-written reason on step 6 was wrong once and
//     nearly entered a gate report as an observation.
//
// R3. The instrument never works around a product defect. If it needs a
//     workaround to proceed, the workaround IS the finding.
//
// R4. Findings are labelled by source — BUILD, RENDERED UI, NETWORK — and
//     never blurred. They are different quality evidence.
//
// R5. Assert outcomes (a match count, an ITC figure, a status transition),
//     never "the page loaded".

import { execSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");

// Playwright lives in frontend/node_modules, not at the repo root, so a
// bare `import "playwright"` from docs/readiness/ does not resolve. Resolve
// it explicitly against the frontend package rather than requiring callers
// to symlink node_modules into the repo root.
const { chromium } = createRequire(path.join(REPO, "frontend", "package.json"))("playwright");
const REGISTER_CSV = path.join(HERE, "walkthrough-register.csv");
const FIXTURE_DIR = path.join(REPO, "backend", "app", "gsp", "fixtures");

// Every `docker compose` call below picks up the readiness overlay, which
// serves the frontend with `next start` instead of `next dev`.
process.env.COMPOSE_FILE = [
  path.join(REPO, "docker-compose.yml"),
  path.join(HERE, "docker-compose.readiness.yml"),
].join(path.delimiter);

const BASE = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const API = process.env.NIYAM_API_BASE || "http://localhost:8000";

// ─── TOTP (RFC 6238, SHA-1, 6 digits, 30s window) ───
function base32Decode(s) {
  const alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  s = s.replace(/=+$/, "").toUpperCase();
  const bytes = [];
  let bits = 0, buf = 0;
  for (const c of s) {
    const v = alpha.indexOf(c);
    if (v < 0) continue;
    buf = (buf << 5) | v;
    bits += 5;
    if (bits >= 8) { bits -= 8; bytes.push((buf >> bits) & 0xff); }
  }
  return Buffer.from(bytes);
}
function totpNow(secret) {
  const counter = Math.floor(Date.now() / 1000 / 30);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const h = crypto.createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const offset = h[h.length - 1] & 0x0f;
  const code = ((h.readUInt32BE(offset) & 0x7fffffff)) % 1_000_000;
  return String(code).padStart(6, "0");
}

const results = [];
function log(step, status, detail) {
  const row = { step, status, ...(detail !== undefined ? { detail } : {}) };
  console.log(JSON.stringify(row));
  results.push(row);
}

function sh(cmd, opts = {}) {
  return execSync(cmd, {
    encoding: "utf8",
    cwd: REPO,
    stdio: ["ignore", "pipe", "pipe"],
    ...opts,
  });
}

function bail(step, detail, code = 1) {
  log(step, "STOPPED", detail);
  console.log("\n---SUMMARY---");
  console.log(JSON.stringify(results, null, 2));
  process.exit(code);
}

// ─────────────────────────────────────────────────────────────────────────
// Observability. Four separate channels — mixing them is how a build
// failure once masqueraded as a missing UI element.
// ─────────────────────────────────────────────────────────────────────────
const consoleMessages = [];   // every browser console message, with level
const pageErrors = [];        // uncaught exceptions in the page, with stack
const requestFailures = [];   // transport-level failures (DNS, refused, abort)
const httpErrors = [];        // HTTP 4xx/5xx responses

// A cursor marks a point in each channel plus wall-clock, so a step can
// report only what happened during that step rather than the whole run.
function mark() {
  return {
    t: Date.now(),
    console: consoleMessages.length,
    pageErrors: pageErrors.length,
    requestFailures: requestFailures.length,
    httpErrors: httpErrors.length,
  };
}
function since(cursor) {
  return {
    consoleErrors: consoleMessages
      .slice(cursor.console)
      .filter((m) => m.type === "error" || m.type === "warning"),
    pageErrors: pageErrors.slice(cursor.pageErrors),
    requestFailures: requestFailures.slice(cursor.requestFailures),
    // The two-step login handshake returns 400 totp_required by design.
    // It is not an error; excluding it keeps real 4xx visible.
    httpErrors: httpErrors
      .slice(cursor.httpErrors)
      .filter((e) => !(e.status === 400 && /\/auth\/login$/.test(e.url))),
  };
}

// ─── BUILD channel: frontend container log scraping ───
// A step must never report ok for a route that did not compile. In a
// production build this should stay empty; if it does not, the compile
// error is attached to whichever step was executing.
const BUILD_ERROR_RE = /FATAL|Failed to compile|Next\.js package not found|Module not found|Unhandled Runtime Error|Internal Server Error/i;
function frontendBuildErrorsSince(cursor) {
  const seconds = Math.max(1, Math.ceil((Date.now() - cursor.t) / 1000) + 2);
  let out = "";
  try {
    out = sh(`docker compose logs frontend --since=${seconds}s --no-color 2>&1`);
  } catch (e) {
    return [{ note: `could not read frontend logs: ${String(e.message).slice(0, 120)}` }];
  }
  return out
    .split("\n")
    .filter((l) => BUILD_ERROR_RE.test(l))
    .slice(0, 8)
    .map((l) => l.slice(0, 300));
}

// ─────────────────────────────────────────────────────────────────────────
// Step 0 — production build. Captured explicitly so a build failure is a
// reported finding with its output, not a container restart loop.
// ─────────────────────────────────────────────────────────────────────────
if (process.env.NIYAM_SKIP_BUILD === "1") {
  log("0.frontend-build", "SKIPPED", {
    reason: "NIYAM_SKIP_BUILD=1 set explicitly. The run below measures whatever is already serving on :3000 — it does not establish that a production build succeeds.",
  });
} else {
  try {
    sh(`docker compose up -d postgres redis api gsp-mock`, { stdio: ["ignore", "pipe", "pipe"] });
  } catch (err) {
    bail("0.stack-up", { at: String(err.stderr || err.message).slice(0, 600) });
  }
  let buildOut = "";
  try {
    buildOut = sh(`docker compose run --rm -T frontend npm run build 2>&1`, { timeout: 900_000 });
  } catch (err) {
    const out = String(err.stdout || "") + String(err.stderr || "");
    bail("0.frontend-build", {
      source: "BUILD",
      reason: "Production build failed. The walkthrough cannot measure the product through a build that does not exist.",
      output: out.split("\n").slice(-60).join("\n").slice(0, 4000),
    });
  }
  const warnings = buildOut
    .split("\n")
    .filter((l) => /warn|error/i.test(l))
    .slice(0, 15)
    .map((l) => l.trim().slice(0, 220));
  log("0.frontend-build", "ok", {
    source: "BUILD",
    tail: buildOut.split("\n").filter(Boolean).slice(-12).map((l) => l.slice(0, 220)),
    warnings,
  });

  try {
    sh(`docker compose up -d --force-recreate frontend`, { stdio: ["ignore", "pipe", "pipe"] });
  } catch (err) {
    bail("0.frontend-start", { at: String(err.stderr || err.message).slice(0, 600) });
  }
  // Wait for `next start` to actually serve. If it never does, the frontend
  // log is the finding.
  const deadline = Date.now() + 120_000;
  let served = false;
  while (Date.now() < deadline) {
    try {
      sh(`curl -sf -o /dev/null ${BASE}`);
      served = true;
      break;
    } catch {
      // Not serving yet. Sleep between probes rather than spinning — a hot
      // loop here would burn a core for up to two minutes.
      try { sh(`sleep 2`); } catch {}
    }
  }
  if (!served) {
    let tail = "";
    try { tail = sh(`docker compose logs frontend --tail=40 --no-color 2>&1`); } catch {}
    bail("0.frontend-start", {
      source: "BUILD",
      reason: `next start did not serve ${BASE} within 120s`,
      log: tail.split("\n").slice(-30).join("\n").slice(0, 3000),
    });
  }
  log("0.frontend-start", "ok", { source: "BUILD", mode: "next start (production build)" });
}

// ─────────────────────────────────────────────────────────────────────────
// Prep — destructive guard, truncate, bootstrap
// ─────────────────────────────────────────────────────────────────────────
// Refuse to truncate unless the target is demonstrably local. The compose
// stack pins postgres at 127.0.0.1:5432 in dev; if anyone ever exports
// POSTGRES_HOST to reach a staging or prod DB and then runs this script,
// the TRUNCATE below would wipe production.
try {
  const hostInfo = sh(
    `docker compose exec -T postgres psql -U niyam -d niyam -tAc ` +
    `"SELECT COALESCE(inet_server_addr()::text, 'unix-socket') || '|' || COALESCE(inet_client_addr()::text, '')"`,
  ).trim();
  const [srvAddr, cliAddr] = hostInfo.split("|");
  const localRe = /^(127\.|172\.|10\.|192\.168\.|unix-socket$)/;
  if (!localRe.test(srvAddr) || !(!cliAddr || localRe.test(cliAddr))) {
    bail("prep.guard", {
      reason: `refusing to TRUNCATE — server addr '${srvAddr}', client addr '${cliAddr}' are not both in local/private ranges. Set NIYAM_ALLOW_DESTRUCTIVE_TRUNCATE=1 to override.`,
    }, 2);
  }
  if (
    process.env.PLAYWRIGHT_BASE_URL &&
    !/localhost|127\.0\.0\.1/.test(process.env.PLAYWRIGHT_BASE_URL) &&
    process.env.NIYAM_ALLOW_DESTRUCTIVE_TRUNCATE !== "1"
  ) {
    bail("prep.guard", {
      reason: `PLAYWRIGHT_BASE_URL='${process.env.PLAYWRIGHT_BASE_URL}' is not a localhost URL. Set NIYAM_ALLOW_DESTRUCTIVE_TRUNCATE=1 to override.`,
    }, 2);
  }
  log("prep.guard", "ok", { srvAddr, cliAddr });
} catch (err) {
  bail("prep.guard", { at: String(err.message).slice(0, 200) });
}

// Which GSTIN/period actually has mock 2B data? Discovered from the fixture
// directory rather than hardcoded, so the instrument reports the constraint
// instead of silently pulling a period with no data behind it.
let FIXTURE_GSTIN = "29ADVRS0000A1ZA";
let FIXTURE_PERIOD = null;
try {
  const fixtures = fs.readdirSync(FIXTURE_DIR)
    .map((f) => /^gstr2b_([0-9A-Z]+)_(\d{6})\.json$/.exec(f))
    .filter(Boolean)
    .map((m) => ({ gstin: m[1], period: m[2] }));
  const forGstin = fixtures.filter((f) => f.gstin === FIXTURE_GSTIN);
  const chosen = (forGstin.length ? forGstin : fixtures).sort((a, b) => b.period.localeCompare(a.period))[0];
  if (chosen) { FIXTURE_GSTIN = chosen.gstin; FIXTURE_PERIOD = chosen.period; }
  log("prep.fixture", FIXTURE_PERIOD ? "ok" : "STOPPED", {
    gstin: FIXTURE_GSTIN,
    period: FIXTURE_PERIOD,
    available: fixtures.map((f) => `${f.gstin}@${f.period}`),
  });
  if (!FIXTURE_PERIOD) bail("prep.fixture", { reason: "no mock 2B fixture found — the pull step cannot assert an outcome" });
} catch (err) {
  bail("prep.fixture", { at: String(err.message).slice(0, 300) });
}

let creds;
try {
  sh(`docker compose exec -T postgres psql -U niyam -d niyam -c "TRUNCATE ca_firm CASCADE" >/dev/null`);
  log("prep.truncate", "ok");
  const email = `admin@walkthrough-${Date.now()}.example`;
  const raw = sh(
    `docker compose --profile cli run --rm -T backend python -m app.cli.provision_firm ` +
    `--firm-name "Walkthrough Firm" --admin-email ${email} --auto-accept-legal --json`
  ).trim();
  const jsonLine = raw.split("\n").reverse().find((l) => l.trim().startsWith("{"));
  creds = JSON.parse(jsonLine);
  log("prep.bootstrap", "ok", {
    firm_id: creds.firm_id,
    admin_email: creds.admin_email,
    accepted_docs: creds.accepted_docs,
    note: "accepted_via='bootstrap' — provisioning, never evidence of consent",
  });
} catch (err) {
  bail("prep.bootstrap", { at: String(err.message).slice(0, 400) });
}

// ─────────────────────────────────────────────────────────────────────────
// Browser
// ─────────────────────────────────────────────────────────────────────────
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

page.on("console", (m) => {
  consoleMessages.push({ type: m.type(), text: m.text().slice(0, 400) });
});
page.on("pageerror", (e) => {
  pageErrors.push({
    message: String(e.message).slice(0, 400),
    stack: String(e.stack || "").split("\n").slice(0, 6).join("\n").slice(0, 800),
  });
});
page.on("requestfailed", (r) => {
  requestFailures.push({
    url: r.url().slice(0, 300),
    method: r.method(),
    failure: r.failure()?.errorText ?? "unknown",
  });
});
page.on("response", async (r) => {
  const s = r.status();
  if (s >= 400) {
    let body = "";
    try { body = (await r.text()).slice(0, 300); } catch {}
    httpErrors.push({ url: r.url(), status: s, body });
  }
});

async function firstVisible(locators) {
  for (const l of locators) {
    if ((await l.count()) > 0 && (await l.first().isVisible().catch(() => false))) {
      return l.first();
    }
  }
  return null;
}

// Next.js surfaces failures differently in dev (overlay) and production
// (a generic error shell). Check for both.
async function errorSurface() {
  const overlay = page.locator("nextjs-portal, [data-nextjs-dialog], #nextjs__container_errors_label");
  if ((await overlay.count().catch(() => 0)) > 0) {
    const text = await overlay.first().innerText().catch(() => "");
    return { kind: "nextjs-error-overlay", text: text.slice(0, 600) };
  }
  const body = await page.locator("body").innerText().catch(() => "");
  if (/Application error: a (client|server)-side exception has occurred/i.test(body)) {
    return { kind: "nextjs-production-error-shell", text: body.slice(0, 400) };
  }
  if (/^\s*(404|500)\b|This page could not be found/i.test(body)) {
    return { kind: "nextjs-error-page", text: body.slice(0, 300) };
  }
  return null;
}

// Derives why something expected on the page is not there. Returns an
// evidence bundle and a cause ONLY when the evidence supports one.
async function diagnose(cursor, expected) {
  const ev = since(cursor);
  const surface = await errorSurface();
  const buildErrors = frontendBuildErrorsSince(cursor);
  const mainCount = await page.locator("main").count().catch(() => 0);
  const mainText = await page.locator("main").innerText().catch(() => "");
  const testids = await page
    .locator("[data-testid]")
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")).slice(0, 40))
    .catch(() => []);

  let cause = "cause not established";
  if (surface) cause = `${surface.kind} on the page`;
  else if (buildErrors.length) cause = "frontend build/compile error during this step";
  else if (ev.pageErrors.length) cause = "uncaught exception in the page during this step";
  else if (ev.requestFailures.length) cause = "transport-level request failure during this step";
  else if (mainCount === 0) cause = "no <main> element — the app shell did not render";
  else if (testids.length === 0) cause = "<main> rendered but contains no instrumented elements";
  else if (ev.httpErrors.length) cause = "HTTP error response during this step";

  return {
    expected,
    cause,
    RENDERED_UI: {
      url: page.url(),
      errorSurface: surface,
      mainElementCount: mainCount,
      mainText: mainText.replace(/\s+/g, " ").slice(0, 500),
      testidsPresent: testids,
    },
    NETWORK: {
      httpErrors: ev.httpErrors,
      requestFailures: ev.requestFailures,
    },
    BUILD: { frontendLogErrors: buildErrors },
    CONSOLE: { errors: ev.consoleErrors.slice(0, 10), pageErrors: ev.pageErrors },
  };
}

// Read the firm's immutable action log through the product's own
// /audit-log surface, carrying the same bearer token the app uses. Going
// through the API rather than psql proves the row is *retrievable by the
// CA*, not merely present in a table.
async function auditRows(entityId, actionPrefix) {
  const token = await page.evaluate(() => window.localStorage.getItem("niyam.access_token"));
  const r = await page.request.get(
    `${API}/audit-log?entity_type=filing_run&entity_id=${entityId}&action_prefix=${actionPrefix}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (r.status() >= 400) {
    return { error: `GET /audit-log returned ${r.status()}`, rows: [] };
  }
  const rows = await r.json().catch(() => []);
  return { rows: Array.isArray(rows) ? rows : [] };
}

// I3 (the log is immutable and load-bearing) and I6 (a figure without a
// retrievable provenance trail is not defensible) both depend on the
// approving user and the time being recorded. If that silently stopped
// happening, no current test would notice — the status pill would still
// read "filed". Assert the provenance, not just the transition.
async function assertAuditProvenance(entityId, actionPrefix, expectEmail) {
  const { rows, error } = await auditRows(entityId, actionPrefix);
  if (error) return { ok: false, why: error };
  if (!rows.length) {
    return { ok: false, why: `no audit_log row with action prefix '${actionPrefix}' for filing_run ${entityId}` };
  }
  const row = rows[0];
  const problems = [];
  if (!row.user_id) problems.push("user_id is null — the acting user was not recorded");
  if (expectEmail && row.user_email !== expectEmail) {
    problems.push(`user_email '${row.user_email}' does not match the acting user '${expectEmail}'`);
  }
  if (!row.at || Number.isNaN(Date.parse(row.at))) {
    problems.push(`'at' is missing or unparseable: ${JSON.stringify(row.at)}`);
  }
  return {
    ok: problems.length === 0,
    why: problems.join("; "),
    row: { action: row.action, user_id: row.user_id, user_email: row.user_email, at: row.at, diff: row.diff },
    rowCount: rows.length,
  };
}

async function stop(step, detail) {
  log(step, "STOPPED", detail);
  await browser.close();
  console.log("\n---SUMMARY---");
  console.log(JSON.stringify(results, null, 2));
  process.exit(0);
}

// Navigate and verify a real document came back and rendered.
async function gotoChecked(url, stepName) {
  const cursor = mark();
  const resp = await page.goto(url, { waitUntil: "networkidle" }).catch((e) => {
    return { __navError: String(e.message).slice(0, 300) };
  });
  if (resp && resp.__navError) {
    await stop(stepName, { source: "NETWORK", reason: `navigation to ${url} threw`, error: resp.__navError, ...(await diagnose(cursor, url)) });
  }
  const status = typeof resp?.status === "function" ? resp.status() : null;
  if (status !== null && status >= 400) {
    await stop(stepName, { source: "NETWORK", reason: `${url} returned HTTP ${status}`, ...(await diagnose(cursor, url)) });
  }
  const surface = await errorSurface();
  const buildErrors = frontendBuildErrorsSince(cursor);
  if (surface || buildErrors.length) {
    await stop(stepName, {
      source: surface ? "RENDERED_UI" : "BUILD",
      reason: "route did not render a healthy document",
      ...(await diagnose(cursor, url)),
    });
  }
  return { status, cursor };
}

await (async () => {
try {
  // ─── Step 1: sign in ───
  let c = mark();
  await gotoChecked(`${BASE}/v2/sign-in`, "1.load-signin");
  log("1.load-signin", "ok", { url: page.url() });

  const emailInput = await firstVisible([
    page.getByLabel(/work email|email/i),
    page.locator("input[type=email]"),
    page.locator("input[name=email]"),
  ]);
  const passInput = await firstVisible([
    page.getByLabel(/password/i),
    page.locator("input[type=password]"),
  ]);
  if (!emailInput || !passInput) {
    return stop("1.signin-form", { source: "RENDERED_UI", ...(await diagnose(c, "email + password inputs")) });
  }

  await emailInput.fill(creds.admin_email);
  await passInput.fill(creds.admin_password);
  const submit = await firstVisible([
    page.getByRole("button", { name: /^continue$|^sign in$|^log in$/i }),
    page.locator("button[type=submit]"),
  ]);
  if (!submit) return stop("1.signin-submit", { source: "RENDERED_UI", ...(await diagnose(c, "password submit button")) });
  await submit.click();

  // The v2 sign-in page does not navigate on password submit — it
  // transitions local step state and renders <input id="totp">.
  c = mark();
  await page.waitForSelector("#totp", { timeout: 8000 }).catch(() => {});
  const totpInput = await firstVisible([
    page.locator("#totp"),
    page.locator("input[inputmode=numeric][maxlength='6']"),
    page.locator("input[autocomplete='one-time-code']"),
  ]);
  if (!totpInput) {
    return stop("1.totp-challenge", { source: "RENDERED_UI", ...(await diagnose(c, "TOTP input after password submit")) });
  }
  log("1.password-submitted", "ok", { url: page.url(), note: "400 totp_required on first submit is the two-step handshake, not a failure" });

  await totpInput.fill(totpNow(creds.totp_secret));
  const totpSubmit = await firstVisible([
    page.getByRole("button", { name: /verify & sign in/i }),
    page.locator("button[type=submit]:not([disabled])").filter({ hasText: /verify/i }),
  ]);
  if (!totpSubmit) return stop("1.totp-submit", { source: "RENDERED_UI", ...(await diagnose(c, "enabled TOTP submit button")) });
  c = mark();
  await totpSubmit.click();

  // Outcome assertion: a token actually landed, AND the app navigated away
  // from the sign-in page. Token-only is not evidence the session works.
  const tokenLanded = await page.waitForFunction(
    () => !!window.localStorage.getItem("niyam.access_token"),
    { timeout: 10000 },
  ).then(() => true).catch(() => false);
  if (!tokenLanded) {
    return stop("1.signed-in", { source: "RENDERED_UI", ...(await diagnose(c, "niyam.access_token in localStorage")) });
  }
  await page.waitForLoadState("networkidle").catch(() => {});
  const landedAway = !/\/v2\/sign-in\/?$/.test(new URL(page.url()).pathname);
  log("1.signed-in", "ok", {
    url: page.url(),
    tokenLanded,
    navigatedAwayFromSignIn: landedAway,
    ...(landedAway ? {} : { note: "token present but the app did not navigate away from /v2/sign-in — recorded, not treated as a blocker" }),
  });
} catch (err) {
  return stop("1.signin", { source: "RENDERED_UI", error: String(err.message).slice(0, 300), ...(await diagnose(mark(), "sign-in flow")) });
}

let gstinProfileId = null;
let gstinBody = "";
let filingId = null;

try {
  // ─── Step 2: create a client via legacy /settings ───
  let c = mark();
  await gotoChecked(`${BASE}/settings`, "2.load-settings");
  log("2.load-settings", "ok", { url: page.url() });

  const tradeName = page.locator("input[name='trade_name']");
  if ((await tradeName.count()) === 0) {
    return stop("2.client-form", { source: "RENDERED_UI", ...(await diagnose(c, "input[name='trade_name'] on /settings")) });
  }
  await tradeName.first().fill("Walkthrough Client");
  const createClient = await firstVisible([
    page.getByRole("button", { name: /^create$|create client|add client/i }),
    page.locator("button[type=submit]").filter({ hasText: /create|add/i }),
  ]);
  if (!createClient) return stop("2.client-submit", { source: "RENDERED_UI", ...(await diagnose(c, "create-client submit button")) });
  c = mark();
  await createClient.click();
  const clientResp = await page.waitForResponse(
    (r) => r.url().endsWith("/clients") && r.request().method() === "POST",
    { timeout: 8000 },
  ).catch(() => null);
  if (!clientResp) {
    return stop("2.client-created", { source: "NETWORK", ...(await diagnose(c, "POST /clients response within 8s")) });
  }
  if (clientResp.status() >= 400) {
    return stop("2.client-created", {
      source: "NETWORK",
      reason: `POST /clients returned ${clientResp.status()}`,
      body: (await clientResp.text().catch(() => "")).slice(0, 300),
    });
  }
  log("2.client-created", "ok", { status: clientResp.status() });

  // ─── Step 3: add a GSTIN ───
  c = mark();
  await gotoChecked(`${BASE}/settings`, "3.reload-settings");
  const toggle = await firstVisible([page.getByRole("button", { name: /\+ add gstin/i })]);
  if (!toggle) return stop("3.gstin-toggle", { source: "RENDERED_UI", ...(await diagnose(c, "'+ Add GSTIN' toggle")) });
  await toggle.click();
  const gstinInput = page.locator("input[name='gstin']").first();
  const stateInput = page.locator("input[name='state_code']").first();
  if ((await gstinInput.count()) === 0 || (await stateInput.count()) === 0) {
    return stop("3.gstin-form", { source: "RENDERED_UI", ...(await diagnose(c, "gstin + state_code inputs after toggle")) });
  }
  await gstinInput.fill(FIXTURE_GSTIN);
  await stateInput.fill(FIXTURE_GSTIN.slice(0, 2));
  const addBtn = await firstVisible([page.getByRole("button", { name: /^add gstin$/i })]);
  if (!addBtn) return stop("3.gstin-submit", { source: "RENDERED_UI", ...(await diagnose(c, "'Add GSTIN' submit button")) });
  c = mark();
  await addBtn.click();
  const gstinResp = await page.waitForResponse(
    (r) => /\/clients\/[^/]+\/gstins$/.test(r.url()) && r.request().method() === "POST",
    { timeout: 8000 },
  ).catch(() => null);
  if (!gstinResp) {
    return stop("3.gstin-added", { source: "NETWORK", ...(await diagnose(c, "POST /clients/{id}/gstins response within 8s")) });
  }
  gstinBody = await gstinResp.text().catch(() => "");
  if (gstinResp.status() >= 400) {
    return stop("3.gstin-added", { source: "NETWORK", reason: `POST /gstins returned ${gstinResp.status()}`, body: gstinBody.slice(0, 300) });
  }
  gstinProfileId = /"id":"([^"]+)"/.exec(gstinBody)?.[1] ?? null;
  log("3.gstin-added", "ok", { status: gstinResp.status(), gstin: FIXTURE_GSTIN, gstin_profile_id: gstinProfileId });

  // ─── Step 4: reach the workspace via the in-product link ───
  c = mark();
  await page.waitForSelector('a:has-text("Open workspace")', { timeout: 8000 }).catch(() => {});
  const workspaceLink = await firstVisible([
    page.getByRole("link", { name: /open workspace/i }),
    page.locator('a[href*="/workspace/"]'),
  ]);
  if (!workspaceLink) {
    return stop("4.reach-workspace", { source: "RENDERED_UI", ...(await diagnose(c, "'Open workspace' link after add-GSTIN")) });
  }
  const linkHref = await workspaceLink.getAttribute("href").catch(() => null);
  await workspaceLink.click();
  await page.waitForLoadState("networkidle").catch(() => {});

  // A click is not a navigation. Verify the workspace actually rendered.
  const surface4 = await errorSurface();
  const build4 = frontendBuildErrorsSince(c);
  if (surface4 || build4.length) {
    return stop("4.reached-workspace", {
      source: surface4 ? "RENDERED_UI" : "BUILD",
      reason: "workspace route did not render a healthy document",
      ...(await diagnose(c, "workspace page")),
    });
  }
  const defaultPeriod = new URL(page.url()).searchParams.get("period");
  log("4.reached-workspace", "ok", {
    url: page.url(),
    linkHref,
    defaultPeriod,
    defaultReturnType: new URL(page.url()).searchParams.get("return_type"),
  });

  // The mock GSP only holds 2B for the fixture period. If the product's
  // default period differs, say so — the data steps below run against the
  // fixture period, and that limits what a green run can claim.
  if (defaultPeriod !== FIXTURE_PERIOD) {
    log("4.period-constraint", "NOTE", {
      productDefaultPeriod: defaultPeriod,
      fixturePeriod: FIXTURE_PERIOD,
      effect: `No mock 2B exists for ${defaultPeriod}. Steps 6-13 run against ${FIXTURE_PERIOD} instead. This is a fixture-coverage limit, not a product defect, and it means a green run does not exercise the product's own default period.`,
    });
  }

  // ─── Step 5: workspace tour — observational, does not stop on oddities ───
  c = mark();
  const wsUrl = `${BASE}/workspace/${gstinProfileId}?period=${FIXTURE_PERIOD}&return_type=GSTR1&gstin=${FIXTURE_GSTIN}&client=Walkthrough+Client`;
  await gotoChecked(wsUrl, "5.workspace-tour");

  const observations = [];
  const tabsVisible = await page
    .locator('[data-testid^="tab-"]')
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")))
    .catch(() => []);
  observations.push({ what: "workspace-tabs-visible", value: tabsVisible });

  for (const tabName of ["invoices", "reconciliation", "returns", "filings", "ocr"]) {
    const tabBtn = await firstVisible([page.locator(`[data-testid="tab-${tabName}"]`)]);
    if (!tabBtn) {
      observations.push({ what: `tab.${tabName}`, status: "absent", ...(await diagnose(c, `tab-${tabName}`)) });
      continue;
    }
    await tabBtn.click().catch(() => {});
    await page.waitForLoadState("networkidle").catch(() => {});
    const mainText = await page.locator("main").innerText().catch(() => "");
    observations.push({
      what: `tab.${tabName}`,
      status: "ok",
      textSample: mainText.replace(/\s+/g, " ").slice(0, 200),
      hasObjectObject: /\[object Object\]/.test(mainText),
    });
  }
  const ev5 = since(c);
  log("5.workspace-tour", tabsVisible.length === 5 ? "ok" : "PARTIAL", {
    source: "RENDERED_UI",
    tabsFound: tabsVisible.length,
    observations,
    NETWORK: { httpErrors: ev5.httpErrors, requestFailures: ev5.requestFailures },
    CONSOLE: { errors: ev5.consoleErrors.slice(0, 10), pageErrors: ev5.pageErrors },
  });
  if (tabsVisible.length === 0) {
    return stop("5.workspace-tour", { source: "RENDERED_UI", reason: "workspace rendered no tabs", ...(await diagnose(c, "five workspace tabs")) });
  }

  // ─── Step 6: GSP connect affordance ───
  c = mark();
  await gotoChecked(wsUrl, "6.gsp-connect");
  const gspAffordance = await firstVisible([
    page.locator("[data-testid=connect-btn]"),
    page.getByRole("button", { name: /connect gsp|connect gstn|consent|^connect$/i }),
    page.getByRole("link", { name: /connect gsp|connect gstn|consent/i }),
  ]);
  if (!gspAffordance) {
    return stop("6.gsp-connect", { source: "RENDERED_UI", ...(await diagnose(c, "GSP connect affordance for an unconnected GSTIN")) });
  }
  log("6.gsp-connect", "ok", { affordanceFound: true });

  // ─── Step 7: Connect → OTP → confirm ───
  c = mark();
  await gspAffordance.click();
  const otpForm = await page.waitForSelector('[data-testid="otp-form"]', { timeout: 10000 }).catch(() => null);
  if (!otpForm) {
    return stop("7.otp-form", { source: "RENDERED_UI", ...(await diagnose(c, "[data-testid=otp-form] after clicking connect")) });
  }
  await page.locator('[data-testid="otp-form"] input[aria-label="OTP"]').fill("123456");
  c = mark();
  await page.locator('[data-testid="otp-submit"]').click();
  const pullSel = await page.waitForSelector('[data-testid="pull-now"]', { timeout: 12000 }).catch(() => null);
  if (!pullSel) {
    return stop("7.connected", { source: "RENDERED_UI", ...(await diagnose(c, "[data-testid=pull-now] after OTP confirm — the healthy connection state")) });
  }
  log("7.connected", "ok", { note: "connection is against the MOCK GSP adapter, not live GSTN" });

  // ─── Step 8: pull 2B, assert an outcome ───
  c = mark();
  await page.locator('[data-testid="pull-now"]').click();
  const pullResp = await page.waitForResponse(
    (r) => r.url().includes("/gsp/pull") && r.request().method() === "POST",
    { timeout: 20000 },
  ).catch(() => null);
  if (!pullResp) return stop("8.pull", { source: "NETWORK", ...(await diagnose(c, "POST /gsp/pull response")) });
  const pullBody = await pullResp.text().catch(() => "");
  if (pullResp.status() >= 400) {
    return stop("8.pull", { source: "NETWORK", reason: `/gsp/pull returned ${pullResp.status()}`, body: pullBody.slice(0, 300) });
  }
  const pullJson = (() => { try { return JSON.parse(pullBody); } catch { return {}; } })();
  const accepted = pullJson.accepted ?? 0;
  if (!(accepted > 0)) {
    return stop("8.pull-accepted", {
      source: "NETWORK",
      reason: `2B pull succeeded but accepted ${accepted} rows — no data to reconcile, so nothing downstream can be proven`,
      body: pullBody.slice(0, 300),
    });
  }
  log("8.pull-accepted", "ok", { accepted, period: FIXTURE_PERIOD });

  // ─── Step 9: upload the purchase register ───
  c = mark();
  await gotoChecked(`${BASE}/imports`, "9.load-imports");
  if (!fs.existsSync(REGISTER_CSV)) {
    return stop("9.register-fixture", { source: "BUILD", reason: `register fixture missing at ${REGISTER_CSV}` });
  }
  await page.locator('input[placeholder="uuid"]').first().fill(gstinProfileId || "");
  const purchaseForm = page.locator("form").filter({ hasText: /Upload purchase register/i }).first();
  await purchaseForm.locator('input[type="file"]').setInputFiles(REGISTER_CSV);
  c = mark();
  await purchaseForm.locator('button:has-text("Upload purchase register")').click();
  const uploadResp = await page.waitForResponse(
    (r) => r.url().endsWith("/imports/invoices") && r.request().method() === "POST",
    { timeout: 15000 },
  ).catch(() => null);
  if (!uploadResp) return stop("9.register-uploaded", { source: "NETWORK", ...(await diagnose(c, "POST /imports/invoices response")) });
  const upBody = await uploadResp.text().catch(() => "");
  if (uploadResp.status() >= 400) {
    return stop("9.register-uploaded", { source: "NETWORK", reason: `/imports/invoices returned ${uploadResp.status()}`, body: upBody.slice(0, 300) });
  }
  log("9.register-uploaded", "ok", { status: uploadResp.status(), body: upBody.slice(0, 200) });

  // ─── Step 10: trigger reconciliation from the browser ───
  c = mark();
  await gotoChecked(
    `${BASE}/workspace/${gstinProfileId}?period=${FIXTURE_PERIOD}&return_type=GSTR1&gstin=${FIXTURE_GSTIN}&tab=reconciliation`,
    "10.load-reconciliation",
  );
  const reconTrigger = await firstVisible([
    page.locator("[data-testid=run-reconciliation]"),
    page.getByRole("button", { name: /run reconciliation|^reconcile$|start reconciliation/i }),
  ]);
  if (!reconTrigger) {
    return stop("10.reconciliation-trigger", { source: "RENDERED_UI", ...(await diagnose(c, "a browser affordance to trigger a reconciliation run")) });
  }
  await reconTrigger.click();
  const reconResp = await page.waitForResponse(
    (r) => /\/engines\/reconcile/.test(r.url()) && r.request().method() === "POST",
    { timeout: 30000 },
  ).catch(() => null);
  if (!reconResp) return stop("10.reconciliation-run", { source: "NETWORK", ...(await diagnose(c, "POST /engines/reconcile response")) });
  if (reconResp.status() >= 400) {
    return stop("10.reconciliation-run", { source: "NETWORK", reason: `/engines/reconcile returned ${reconResp.status()}`, body: (await reconResp.text().catch(() => "")).slice(0, 300) });
  }
  // Outcome assertion: bucket counts rendered, not "the page loaded".
  await page.waitForLoadState("networkidle").catch(() => {});
  const buckets = {};
  for (const b of ["matched", "probable", "supplier_default", "missing_entry"]) {
    const el = page.locator(`[data-testid="bucket-${b}"]`);
    buckets[b] = (await el.count()) ? (await el.first().innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 60) : null;
  }
  log("10.reconciliation-run", "ok", { source: "RENDERED_UI", buckets });

  // ─── Step 11: generate the return ───
  c = mark();
  await gotoChecked(
    `${BASE}/workspace/${gstinProfileId}?period=${FIXTURE_PERIOD}&return_type=GSTR3B&gstin=${FIXTURE_GSTIN}&tab=filings`,
    "11.load-filings",
  );
  const genBtn = await firstVisible([page.locator("[data-testid=filings-generate]")]);
  if (!genBtn) return stop("11.filing-generate", { source: "RENDERED_UI", ...(await diagnose(c, "[data-testid=filings-generate]")) });
  await genBtn.click();
  const genResp = await page.waitForResponse(
    (r) => r.url().includes("/filings/generate") && r.request().method() === "POST",
    { timeout: 20000 },
  ).catch(() => null);
  if (!genResp) return stop("11.filing-generate", { source: "NETWORK", ...(await diagnose(c, "POST /filings/generate response")) });
  const genBody = await genResp.text().catch(() => "");
  if (genResp.status() >= 400) {
    return stop("11.filing-generate", { source: "NETWORK", reason: `/filings/generate returned ${genResp.status()}`, body: genBody.slice(0, 300) });
  }
  filingId = (() => { try { return JSON.parse(genBody).id ?? null; } catch { return null; } })();
  await page.waitForLoadState("networkidle").catch(() => {});
  const statusAfterGen = await page.locator("[data-testid=filings-status]").innerText().catch(() => "");
  if (!/draft/i.test(statusAfterGen)) {
    return stop("11.filing-generate", { source: "RENDERED_UI", reason: `expected status 'draft' after generate, rendered '${statusAfterGen}'`, ...(await diagnose(c, "filings-status = draft")) });
  }
  log("11.filing-generated", "ok", { source: "RENDERED_UI", status: statusAfterGen.trim(), filing_run_id: filingId });
  if (!filingId) {
    return stop("11.filing-generated", {
      source: "NETWORK",
      reason: "POST /filings/generate returned no filing id, so approval provenance cannot be asserted downstream",
      body: genBody.slice(0, 300),
    });
  }

  // ─── Step 12: approve ───
  c = mark();
  const approveBtn = await firstVisible([page.locator("[data-testid=filings-approve]")]);
  if (!approveBtn) return stop("12.filing-approve", { source: "RENDERED_UI", ...(await diagnose(c, "[data-testid=filings-approve]")) });
  await approveBtn.click();
  await page.waitForLoadState("networkidle").catch(() => {});
  const statusAfterApprove = await page.locator("[data-testid=filings-status]").innerText().catch(() => "");
  if (!/approved/i.test(statusAfterApprove)) {
    return stop("12.filing-approve", { source: "RENDERED_UI", reason: `expected status 'approved', rendered '${statusAfterApprove}'`, ...(await diagnose(c, "filings-status = approved")) });
  }
  const approveAudit = await assertAuditProvenance(filingId, "filing.approved", creds.admin_email);
  if (!approveAudit.ok) {
    return stop("12.filing-approve-provenance", {
      source: "NETWORK",
      reason: `status transitioned to 'approved' but the audit trail is incomplete: ${approveAudit.why}`,
      note: "I3/I6 — a status change without a retrievable acting user and timestamp is not defensible eighteen months later, which is the product's entire differentiator.",
      audit: approveAudit.row ?? null,
    });
  }
  log("12.filing-approved", "ok", {
    source: "RENDERED_UI",
    status: statusAfterApprove.trim(),
    auditProvenance: approveAudit.row,
  });

  // ─── Step 13: mark filed — the readiness bar ───
  c = mark();
  const markFiledBtn = await firstVisible([page.locator("[data-testid=filings-mark-filed]")]);
  if (!markFiledBtn) return stop("13.mark-filed", { source: "RENDERED_UI", ...(await diagnose(c, "[data-testid=filings-mark-filed]")) });
  await markFiledBtn.click();
  const arnInput = await firstVisible([page.locator("[data-testid=filings-arn-input]")]);
  if (arnInput) {
    await arnInput.fill(`ARN-WALKTHROUGH-${FIXTURE_PERIOD}`);
    const confirm = await firstVisible([page.locator("[data-testid=filings-arn-confirm]")]);
    if (!confirm) return stop("13.mark-filed", { source: "RENDERED_UI", ...(await diagnose(c, "[data-testid=filings-arn-confirm] after entering ARN")) });
    await confirm.click();
  }
  await page.waitForLoadState("networkidle").catch(() => {});
  const finalStatus = await page.locator("[data-testid=filings-status]").innerText().catch(() => "");
  if (!/filed/i.test(finalStatus)) {
    return stop("13.mark-filed", { source: "RENDERED_UI", reason: `expected status 'filed', rendered '${finalStatus}'`, ...(await diagnose(c, "filings-status = filed")) });
  }
  const filedAudit = await assertAuditProvenance(filingId, "filing.filed", creds.admin_email);
  if (!filedAudit.ok) {
    return stop("13.mark-filed-provenance", {
      source: "NETWORK",
      reason: `status transitioned to 'filed' but the audit trail is incomplete: ${filedAudit.why}`,
      note: "I3/I6 — the filed transition is the one a scrutiny notice asks about. Without the acting user and timestamp it is not evidence.",
      audit: filedAudit.row ?? null,
    });
  }
  log("13.marked-filed", "ok", {
    source: "RENDERED_UI",
    status: finalStatus.trim(),
    auditProvenance: filedAudit.row,
    claim: "The cycle closes against the MOCK GSP adapter. This is not evidence that it closes against live GSTN.",
  });
} catch (err) {
  return stop("uncaught", {
    error: String(err.message).slice(0, 400),
    ...(await diagnose(mark(), "walkthrough continuation")),
  });
}
})();

await browser.close();
console.log("\n---SUMMARY---");
console.log(JSON.stringify(results, null, 2));
