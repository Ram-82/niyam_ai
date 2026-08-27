/**
 * WhatsApp UI adoption e2e — generate narration, approve, send, see attempt.
 *
 * Prereqs:
 *   - docker compose up -d postgres redis api
 *   - frontend dev server on :3000
 *   - api container has NARRATOR_ENABLED=1 + WHATSAPP_ENABLED=1 in its env
 *     (docker-compose override for the e2e profile). Without the flags the
 *     panel renders the "disabled" callout and the test skips the send
 *     assertions rather than failing — see checkFeatureFlags below.
 *
 * Uses the mock narrator (deterministic template) + the mock whatsapp
 * transport (deterministic wamid.mock.NNNNNN ids). No external calls.
 */
import { test, expect } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

import { bootstrapFirm } from "./bootstrap";


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
  email: string;
  password: string;
  totpSecret: string;
  token: string;
};


async function seedFirmWithReadiness(): Promise<Ctx> {
  const boot = await bootstrapFirm({
    firmName: "WaCo",
    emailPrefix: "wa",
    clientTradeName: "Beta Traders",
    gstin: "29ABCDE1234F1Z5",
  });
  // Attach whatsapp_number + gstn_pull + reconciliation_run + readiness_snapshot.
  // The client's whatsapp_number is an UPDATE — POST /clients accepts it but
  // we already created the client through bootstrapFirm without one.
  const seed = `
import json
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = "${boot.firmId}"
client_id = "${boot.clientId}"
gstin_id = "${boot.gstinProfileId}"
import uuid
pull_id = uuid.uuid4()
with engine.begin() as c:
    c.execute(text("UPDATE client SET whatsapp_number = :wn WHERE id = :c"),
              {"c": client_id, "wn": "+919876543210"})
    # narration/facts_builder pulls from readiness_snapshot + reconciliation_run.
    c.execute(text(
        "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, return_type, period, "
        "raw_payload, source) VALUES (:pid, :f, :g, 'GSTR2B', '202607', "
        "CAST('{}' AS JSONB), 'json_import')"),
        {"pid": pull_id, "f": firm_id, "g": gstin_id})
    c.execute(text(
        "INSERT INTO reconciliation_run (firm_id, gstin_profile_id, period, "
        "rule_pack_version, gstn_pull_id, summary) VALUES "
        "(:f, :g, '202607', '1.0.0', :pid, CAST(:s AS JSONB))"),
        {"f": firm_id, "g": gstin_id, "pid": pull_id,
         "s": json.dumps({
             "matched": {"count": 3, "paise": 25000000},
             "probable": {"count": 2, "paise": 15000000},
             "supplier_default": {"count": 6, "paise": 4300000, "top_suppliers": []},
             "missing_entry": {"count": 4, "paise": 12000000},
         })})
    c.execute(text(
        "INSERT INTO readiness_snapshot (firm_id, gstin_profile_id, return_type, "
        "period, score, blockers, arithmetic, rule_pack_version) VALUES "
        "(:f, :g, 'GSTR1', '202607', 65, CAST(:b AS JSONB), CAST(:a AS JSONB), '1.0.0')"),
        {"f": firm_id, "g": gstin_id,
         "b": json.dumps([{
             "kind": "supplier_default", "owner": "ca",
             "description": "ITC at risk from 6 suppliers",
             "paise_impact": 4300000,
         }]),
         "a": json.dumps({"tax_paid_paise": 2500000, "tax_due_paise": 3000000})})
`;
  runInBackend(seed);

  return {
    firmId: boot.firmId,
    gstinProfileId: boot.gstinProfileId,
    email: boot.email,
    password: boot.password,
    totpSecret: boot.totpSecret,
    token: boot.token,
  };
}


/** Probe /narrator/preview + /whatsapp/attempts. If either 503s the
 * feature flag is off and the "happy path" send assertions will skip.
 */
async function checkFeatureFlags(token: string): Promise<{
  narratorOn: boolean;
  whatsappOn: boolean;
}> {
  const narrRes = await fetch(`${API}/narrator/runs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const waRes = await fetch(`${API}/whatsapp/attempts`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return {
    narratorOn: narrRes.status !== 503,
    whatsappOn: waRes.status !== 503,
  };
}


let ctx: Ctx;
test.beforeAll(async () => {
  ctx = await seedFirmWithReadiness();
});


test("delivery panel appears on returns tab with narration + attempts", async ({
  page,
}) => {
  const flags = await checkFeatureFlags(ctx.token);

  await page.goto("/");
  await page.evaluate((tok) => {
    localStorage.setItem("niyam.access_token", tok);
  }, ctx.token);
  await page.goto(
    `/workspace/${ctx.gstinProfileId}?period=202607&return_type=GSTR1&gstin=29ABCDE1234F1Z5&tab=returns`,
  );

  // The panel mounts under the returns tab once a readiness snapshot
  // exists. The seed above created one.
  const panel = page.getByTestId("delivery-panel");
  await expect(panel).toBeVisible();

  if (!flags.narratorOn || !flags.whatsappOn) {
    // With flags off the panel renders the disabled callout; the send
    // assertions below are meaningless. Verify the disabled state and
    // stop there.
    await expect(panel).toContainText(
      /WhatsApp delivery is disabled in this environment|Narrator is disabled/i,
    );
    test.skip(true, "narrator or whatsapp feature flag off — send flow skipped");
    return;
  }

  // Generate narration.
  await page.getByTestId("generate-narration").click();
  await expect(page.getByTestId("narration-preview")).toBeVisible({
    timeout: 10_000,
  });

  // Open prepare modal.
  await page.getByTestId("prepare-delivery").click();
  await expect(page.getByTestId("prepare-modal")).toBeVisible();

  // Phone should be prefilled if the client has one on file — the
  // panel doesn't fetch client details in this first cut, so we type
  // the number here.
  await page.getByTestId("whatsapp-number").fill("+919876543210");

  // Approve & send. This does three backend calls in sequence
  // (create delivery_request → approve → send).
  await page.getByTestId("approve-and-send").click();

  // The attempt row appears with status='sent' (mock transport is
  // synchronous). ``delivery-status-sent`` is stable across the
  // deterministic mock message id.
  await expect(page.getByTestId("delivery-status-sent")).toBeVisible({
    timeout: 10_000,
  });
});
