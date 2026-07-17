/**
 * Test-only seed helper. Called from Playwright smoke to bring the
 * DB to a known state per test: one firm, one admin, one client,
 * one GSTIN profile, invoices + 2B + validation + reconciliation +
 * score already computed.
 *
 * Uses the same HTTP surface a real CA would use — no shortcut to
 * ownership of DB primitives. That way the smoke also tests the API.
 */
import { authenticator } from "otplib";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
// Repo root — docker compose commands must run from where the compose
// file lives. Playwright is invoked from ``frontend/``, so cwd = frontend
// and the parent is the repo root. Using process.cwd() keeps this
// CommonJS-compatible; Playwright's TypeScript transformer compiles to
// CJS by default and ``import.meta.url`` is not available there.
const REPO_ROOT = resolve(process.cwd(), "..");


/**
 * Run a Python script inside the ``backend`` compose service.
 *
 * We pipe the source via stdin (``python -``) instead of ``-c "…"``:
 * shell double-quoted strings preserve backslashes literally, so any
 * newline in the source arrives at Python as a literal ``\n`` which is
 * a syntax error. Piping avoids the shell entirely.
 */
function runInBackend(script: string): string {
  const result = spawnSync(
    "docker",
    ["compose", "run", "--rm", "-T", "backend", "python", "-"],
    {
      input: script,
      cwd: REPO_ROOT,
      encoding: "utf-8",
    }
  );
  if (result.status !== 0) {
    throw new Error(
      `runInBackend failed (status=${result.status})\n` +
      `--- stdout ---\n${result.stdout}\n` +
      `--- stderr ---\n${result.stderr}`
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


/**
 * Bootstrap a firm + admin directly in Postgres via the backend
 * container's shell. We use exec because the API can't create the
 * first firm — that's a chicken-and-egg (there's no admin yet to
 * authenticate the CREATE FIRM call). Real deployment path is a
 * one-off Python script; Playwright uses the same idea inline.
 */
export async function seedFirmAndData(): Promise<Seed> {
  const email = `smoke-${randomUUID()}@example.com`;
  const password = "Correct-Horse-Battery-Staple-42";
  const script = `
import os, uuid, secrets, pyotp, base64
from sqlalchemy import create_engine, text
from app.auth.passwords import hash_password

engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = uuid.uuid4()
user_id = uuid.uuid4()
secret = pyotp.random_base32()

with engine.begin() as conn:
    conn.execute(text("INSERT INTO ca_firm (id, name) VALUES (:id, 'SmokeCo')"), {"id": firm_id})
    conn.execute(
        text("""
            INSERT INTO app_user (
                id, firm_id, email, password_hash, role,
                totp_secret, totp_confirmed, is_active
            ) VALUES (
                :id, :fid, :email, :ph, 'admin',
                :ts, TRUE, TRUE
            )
        """),
        {"id": user_id, "fid": firm_id, "email": ${JSON.stringify(email)},
         "ph": hash_password(${JSON.stringify(password)}), "ts": secret},
    )

print(f"{firm_id}|{user_id}|{secret}")
`;
  const raw = runInBackend(script);
  const line = raw.trim().split(/\r?\n/).pop() || "";
  const [firmId, , totpSecret] = line.split("|");

  // Login via the API so downstream calls use a real access token.
  const totpCode = authenticator.generate(totpSecret);
  const loginRes = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, totp_code: totpCode }),
  });
  const login = await loginRes.json();
  const token = login.access_token;

  // Create a client + gstin_profile via API.
  const clientRes = await fetch(`${API}/clients`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ trade_name: "SmokeClient" }),
  });
  const client = await clientRes.json();

  const gstin = "29AAAAA0000A1ZY";  // pre-verified checksum for tests
  const gRes = await fetch(`${API}/clients/${client.id}/gstins`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      gstin,
      state_code: "29",
      scheme: "regular",
    }),
  });
  const gstinProfile = await gRes.json();

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
  const period = "202606";
  const supA = "29BBBBB1234C2Z8";
  const supB = "27CCCCC5678D3ZE";
  const seedRows = `
import uuid, json
from datetime import date
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = "${firmId}"
gid = "${gstinProfile.id}"
supA = "${supA}"
supB = "${supB}"
pull_id = str(uuid.uuid4())
with engine.begin() as c:
    for num, dt, cp, total in [
        ("M-1",  "2026-06-15", supA, 100000),   # -> matched
        ("P-1",  "2026-06-15", supA, 200000),   # -> probable via P/1
        ("SD-A", "2026-06-15", supA, 400000),   # -> supplier_default WITH near-miss
        ("SD-B", "2026-06-15", supB, 500000),   # -> supplier_default WITHOUT near-miss
    ]:
        # content_hash computed in Python so we pass ONE unambiguous
        # text param (Postgres refuses to type-infer CONCAT of two
        # otherwise-untyped params).
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
        ("M-1",     "2026-06-15", supA, 100000),   # exact match to register M-1
        ("P/1",     "2026-06-17", supA, 200200),   # probable match to register P-1
        ("SD-A",    "2026-06-15", supA, 999000),   # near-miss for register SD-A
        ("GHOST-1", "2026-06-20", supA,   5000),   # missing_entry
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
    ["/engines/validate", { gstin_profile_id: gstinProfile.id, period }],
    ["/engines/reconcile", { gstin_profile_id: gstinProfile.id, period }],
    ["/engines/score", { gstin_profile_id: gstinProfile.id, return_type: "GSTR1", period }],
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
    gstinProfileId: gstinProfile.id,
    period,
    email,
    password,
    totpSecret,
  };
}
