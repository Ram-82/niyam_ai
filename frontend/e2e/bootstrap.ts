/**
 * Shared e2e bootstrap. One definition of "a usable test firm."
 *
 * Every Playwright spec that needs authenticated API access goes through
 * this helper. It creates: firm + admin user (via direct DB — chicken-and-
 * egg for the first user), logs in via /auth/login, accepts every
 * currently-effective legal document via POST /legal/accept, and
 * optionally creates one client + one gstin_profile via /clients and
 * /clients/{id}/gstins.
 *
 * Rationale for calling the acceptance endpoint rather than inserting
 * ``legal_acceptance`` rows directly: acceptance semantics — hash pinning,
 * audit-log co-write, immutable append — live on the write path. A test
 * that bypasses that path silently drifts the moment the manifest changes.
 *
 * If a spec needs extra seed data (invoices, gstn_pull, reconciliation_run,
 * match_result, etc.), it runs its own Python script AFTER calling
 * ``bootstrapFirm`` — that data is per-spec and does not belong in
 * the shared surface.
 */
import { authenticator } from "otplib";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
const REPO_ROOT = resolve(process.cwd(), "..");


export type BootstrapOptions = {
  /** Human-readable name stored on ca_firm.name. Default: ``TestFirm-<uuid>``. */
  firmName?: string;
  /** Prefix on the generated admin email. Default: ``e2e``. */
  emailPrefix?: string;
  /** Trade name for the created client. Default: ``TestClient``. */
  clientTradeName?: string;
  /** GSTIN for the created gstin_profile. Default: ``29AAAAA0000A1ZY``. */
  gstin?: string;
  /** Two-digit state code — must match GSTIN[:2] or the API rejects. */
  stateCode?: string;
};


export type Bootstrap = {
  firmId: string;
  userId: string;
  email: string;
  password: string;
  totpSecret: string;
  token: string;
  clientId: string;
  gstinProfileId: string;
};


/**
 * Run a Python script inside the ``backend`` compose service. Piped via
 * stdin rather than ``-c`` because shell double-quoted strings mangle the
 * newlines that Python needs literal.
 */
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


type PendingDoc = {
  doc_type: string;
  version: string;
  content_hash: string;
};


async function acceptAllLegal(token: string): Promise<void> {
  const res = await fetch(`${API}/legal/pending`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(
      `GET /legal/pending failed: ${res.status} ${await res.text()}`,
    );
  }
  const { pending } = (await res.json()) as { pending: PendingDoc[] };
  for (const doc of pending) {
    const acceptRes = await fetch(`${API}/legal/accept`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        doc_type: doc.doc_type,
        version: doc.version,
        content_hash: doc.content_hash,
      }),
    });
    if (!acceptRes.ok) {
      throw new Error(
        `POST /legal/accept ${doc.doc_type}@${doc.version} failed: ` +
        `${acceptRes.status} ${await acceptRes.text()}`,
      );
    }
  }
}


export async function bootstrapFirm(
  opts: BootstrapOptions = {},
): Promise<Bootstrap> {
  const firmName = opts.firmName ?? `TestFirm-${randomUUID().slice(0, 8)}`;
  const emailPrefix = opts.emailPrefix ?? "e2e";
  const email = `${emailPrefix}-${randomUUID()}@example.com`;
  const password = "Correct-Horse-Battery-Staple-42";
  const clientTradeName = opts.clientTradeName ?? "TestClient";
  // Default GSTIN has pre-verified checksum for test use.
  const gstin = opts.gstin ?? "29AAAAA0000A1ZY";
  const stateCode = opts.stateCode ?? gstin.slice(0, 2);

  // Step 1: firm + user directly in Postgres. The first admin of a firm
  // has no invite to accept — that path can't create itself.
  const script = `
import uuid, pyotp
from sqlalchemy import create_engine, text
from app.auth.passwords import hash_password
engine = create_engine("postgresql+psycopg://niyam:niyam@postgres:5432/niyam")
firm_id = uuid.uuid4()
user_id = uuid.uuid4()
secret = pyotp.random_base32()
with engine.begin() as c:
    c.execute(text("INSERT INTO ca_firm (id, name) VALUES (:i, :n)"),
              {"i": firm_id, "n": ${JSON.stringify(firmName)}})
    c.execute(text(
        "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
        "totp_secret, totp_confirmed, is_active) VALUES "
        "(:i, :f, :e, :ph, 'admin', :ts, TRUE, TRUE)"),
        {"i": user_id, "f": firm_id, "e": ${JSON.stringify(email)},
         "ph": hash_password(${JSON.stringify(password)}), "ts": secret})
print(f"{firm_id}|{user_id}|{secret}")
`;
  const line = runInBackend(script).trim().split(/\r?\n/).pop() || "";
  const [firmId, userId, totpSecret] = line.split("|");

  // Step 2: login → token.
  const totpCode = authenticator.generate(totpSecret);
  const loginRes = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, totp_code: totpCode }),
  });
  if (!loginRes.ok) {
    throw new Error(
      `POST /auth/login failed: ${loginRes.status} ${await loginRes.text()}`,
    );
  }
  const { access_token: token } = await loginRes.json();

  // Step 3: accept every currently-effective legal document via the same
  // endpoint a real user would call. Do NOT insert into legal_acceptance
  // directly — hash pinning + audit-log co-write live on the write path.
  await acceptAllLegal(token);

  // Step 4: one client + one gstin_profile via API (both now unblocked
  // by acceptance in step 3).
  const clientRes = await fetch(`${API}/clients`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ trade_name: clientTradeName }),
  });
  if (!clientRes.ok) {
    throw new Error(
      `POST /clients failed: ${clientRes.status} ${await clientRes.text()}`,
    );
  }
  const { id: clientId } = await clientRes.json();

  const gstinRes = await fetch(`${API}/clients/${clientId}/gstins`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      gstin,
      state_code: stateCode,
      scheme: "regular",
    }),
  });
  if (!gstinRes.ok) {
    throw new Error(
      `POST /clients/{id}/gstins failed: ${gstinRes.status} ` +
      `${await gstinRes.text()}`,
    );
  }
  const { id: gstinProfileId } = await gstinRes.json();

  return {
    firmId,
    userId,
    email,
    password,
    totpSecret,
    token,
    clientId,
    gstinProfileId,
  };
}
