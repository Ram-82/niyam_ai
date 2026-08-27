/**
 * Test-only seed helper. Called from Playwright smoke to bring the
 * DB to a known state per test: one firm, one admin, one client,
 * one GSTIN profile, invoices + 2B + validation + reconciliation +
 * score already computed.
 *
 * Firm/user/client/GSTIN/legal-acceptance come from the shared
 * ``bootstrapFirm`` helper. Everything else — the invoice/b2b/gstn_pull
 * scenario the smoke asserts on, plus the engines/validate ·
 * engines/reconcile · engines/score triggers — is smoke-specific and
 * stays here.
 */
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

import { bootstrapFirm } from "./bootstrap";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
const REPO_ROOT = resolve(process.cwd(), "..");


function runInBackend(script: string): string {
  const result = spawnSync(
    "docker",
    ["compose", "run", "--rm", "-T", "backend", "python", "-"],
    { input: script, cwd: REPO_ROOT, encoding: "utf-8" },
  );
  if (result.status !== 0) {
    throw new Error(
      `runInBackend failed (status=${result.status})\n` +
      `--- stdout ---\n${result.stdout}\n` +
      `--- stderr ---\n${result.stderr}`,
    );
  }
  return result.stdout;
}


export type Seed = {
  firmId: string;
  gstinProfileId: string;
  period: string;
  email: string;
  password: string;
  totpSecret: string;
};


export async function seedFirmAndData(): Promise<Seed> {
  const boot = await bootstrapFirm({
    firmName: "SmokeCo",
    emailPrefix: "smoke",
    clientTradeName: "SmokeClient",
  });
  const { firmId, gstinProfileId, email, password, totpSecret, token } = boot;

  // Seed a scenario that produces one row in EVERY reconciliation
  // bucket the smoke needs to assert on:
  //
  //   matched          — M-1 register ↔ M-1 2B, same amount & date.
  //   probable         — P-1 register ↔ P/1 2B, small date + amount drift.
  //   supplier_default WITH near-miss  — SD-A register + SD-A 2B same key
  //                        but amount way outside tolerance: engine
  //                        buckets the register row as supplier_default
  //                        AND surfaces the 2B row as a near-miss.
  //   supplier_default WITHOUT near-miss — SD-B register from a supplier
  //                        that has no 2B entry at all in this period.
  //   missing_entry    — GHOST-1 2B with no register counterpart, PLUS
  //                        the SD-A 2B row (near-misses don't consume it).
  //
  // A second supplier is needed for the "without near-miss" case since
  // near-miss discovery gates on same-supplier.
  //
  // Period: compute last-completed-month at run time (Asia/Kolkata is
  // close enough for a demo — the frontend's ``defaultPeriod`` uses
  // the same calc). Hardcoding "202606" here would silently break the
  // smoke every time the wall-clock month rolls forward, since the
  // frontend's default period would then point at a period with no
  // seed data.
  const now = new Date();
  const firstOfThisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastOfPrev = new Date(firstOfThisMonth.getTime() - 24 * 60 * 60 * 1000);
  const period = `${lastOfPrev.getFullYear().toString().padStart(4, "0")}${(
    lastOfPrev.getMonth() + 1
  )
    .toString()
    .padStart(2, "0")}`;
  const yyyyMm = `${period.slice(0, 4)}-${period.slice(4, 6)}`;
  const midDate = `${yyyyMm}-15`;
  const midPlus2 = `${yyyyMm}-17`;
  const midPlus5 = `${yyyyMm}-20`;
  const supA = "29BBBBB1234C2Z8";
  const supB = "27CCCCC5678D3ZE";
  const seedRows = `
import uuid, json
from datetime import date
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = "${firmId}"
gid = "${gstinProfileId}"
supA = "${supA}"
supB = "${supB}"
pull_id = str(uuid.uuid4())
with engine.begin() as c:
    for num, dt, cp, total in [
        ("M-1",  "${midDate}", supA, 100000),
        ("P-1",  "${midDate}", supA, 200000),
        ("SD-A", "${midDate}", supA, 400000),
        ("SD-B", "${midDate}", supB, 500000),
    ]:
        content_hash = f"h-{num}-{dt}"
        c.execute(text("""
            INSERT INTO invoice (
              firm_id, gstin_profile_id, source, direction,
              invoice_number, invoice_date, counterparty_gstin,
              taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
              total_paise, content_hash
            ) VALUES (:f, :g, 'csv_import', 'purchase',
              :num, :dt, :cp, :total, 0, 0, 0, :total, :h)
        """), {"f": firm_id, "g": gid, "num": num, "dt": dt, "cp": cp,
               "total": total, "h": content_hash})
    c.execute(text("""
        INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, return_type,
          period, raw_payload, source)
        VALUES (:id, :f, :g, 'GSTR2B', '${period}', CAST('{}' AS JSONB), 'json_import')
    """), {"id": pull_id, "f": firm_id, "g": gid})
    for num, dt, sup, tx in [
        ("M-1",     "${midDate}",  supA, 100000),
        ("P/1",     "${midPlus2}", supA, 200200),
        ("SD-A",    "${midDate}",  supA, 999000),
        ("GHOST-1", "${midPlus5}", supA,   5000),
    ]:
        c.execute(text("""
            INSERT INTO b2b_entry (firm_id, gstn_pull_id, supplier_gstin,
              invoice_number, invoice_date, taxable_value_paise,
              tax_paise_breakdown, itc_available)
            VALUES (:f, :pid, :sup, :num, :dt, :tx, CAST('{}' AS JSONB), TRUE)
        """), {"f": firm_id, "pid": pull_id, "sup": sup, "num": num, "dt": dt, "tx": tx})
`;
  runInBackend(seedRows);

  // Trigger validate → reconcile → score via API.
  for (const [path, body] of [
    ["/engines/validate", { gstin_profile_id: gstinProfileId, period }],
    ["/engines/reconcile", { gstin_profile_id: gstinProfileId, period }],
    ["/engines/score", { gstin_profile_id: gstinProfileId, return_type: "GSTR1", period }],
  ] as const) {
    const r = await fetch(`${API}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      throw new Error(`${path} failed: ${r.status} ${await r.text()}`);
    }
  }

  return {
    firmId,
    gstinProfileId,
    period,
    email,
    password,
    totpSecret,
  };
}
