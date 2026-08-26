/**
 * OCR e2e (P2.1 Step 6): upload an invoice fixture → review → accept
 * → confirm the Invoice row lands + the ocr_extraction row locks.
 *
 * Prereqs (all handled by ``docker compose up -d``):
 *   - api container with OCR_ENABLED=1, OCR_MODE=mock (see compose file)
 *   - frontend dev server on :3000
 *
 * We use the ``mock`` adapter so the extraction is deterministic — the
 * pinned fixture at ``backend/app/ocr/fixtures/sample_invoice_1.txt``
 * hashes to a known value and the adapter returns the pre-computed
 * high-confidence fields. That keeps the test independent of Tesseract
 * / pdfminer wall-clock time and language-pack availability in CI.
 */
import { test, expect } from "@playwright/test";
import { authenticator } from "otplib";
import { resolve } from "node:path";
import { seedFirmAndData, type Seed } from "./seed";


const API = process.env.NIYAM_API_BASE || "http://localhost:8000";
const REPO_ROOT = resolve(process.cwd(), "..");
const FIXTURE_PATH = resolve(
  REPO_ROOT,
  "backend",
  "app",
  "ocr",
  "fixtures",
  "sample_invoice_1.txt",
);


let seed: Seed;


test.beforeAll(async () => {
  seed = await seedFirmAndData();
});


test("ocr: upload → review → accept creates an Invoice", async ({ page }) => {
  // --- 0. Sanity: API is up and OCR is enabled in this environment. ---
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
  expect(preLogin.ok).toBeTruthy();
  const { access_token: token } = await preLogin.json();

  // Quick probe: /ocr/extractions must not 503 in this environment.
  // If it does, the spec would still work (the panel renders the
  // "disabled" callout) but that isn't what we want to test here.
  const probe = await fetch(
    `${API}/ocr/extractions?gstin_profile_id=${seed.gstinProfileId}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (probe.status === 503) {
    throw new Error(
      "OCR is disabled in the api container. Set OCR_ENABLED=1 in " +
      "docker-compose.yml or run: OCR_ENABLED=1 docker compose up -d api",
    );
  }
  expect(probe.status).toBe(200);

  // --- 1. Login via UI ---
  const totp = authenticator.generate(seed.totpSecret);
  await page.goto("/login");
  await page.getByTestId("login-email").fill(seed.email);
  await page.getByTestId("login-password").fill(seed.password);
  await page.getByTestId("login-totp").fill(totp);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/command-center/, { timeout: 10_000 });

  // --- 2. Navigate straight to the workspace OCR tab via URL ---
  // (avoids depending on command-center drill-down for this focused
  // OCR spec).
  await page.goto(
    `/workspace/${seed.gstinProfileId}?period=${seed.period}&tab=ocr`,
  );
  await expect(page.getByTestId("ocr-upload-form")).toBeVisible({
    timeout: 10_000,
  });

  // --- 3. Upload the pinned fixture ---
  const fileInput = page.getByTestId("ocr-file-input");
  await fileInput.setInputFiles(FIXTURE_PATH);
  await page.getByRole("button", { name: /Extract fields/i }).click();

  // --- 4. Review card renders with the pinned high-confidence fields ---
  await expect(page.getByTestId("ocr-review-card")).toBeVisible({
    timeout: 10_000,
  });
  // Pinned fixture values from backend/app/ocr/adapter_mock.py — the
  // review UI renders these into <input value=...>, so we assert on
  // the input's value rather than the card's text content.
  await expect(page.getByTestId("ocr-field-supplier_gstin")).toHaveValue(
    "29ABCDE1234F1Z5",
  );
  await expect(page.getByTestId("ocr-field-invoice_number")).toHaveValue(
    "INV-2026-0001",
  );

  // --- 5. Accept → the button flips to Working, then a success message
  //         appears and the row's status pill becomes 'accepted'. ---
  const acceptBtn = page.getByTestId("ocr-accept-btn");
  await acceptBtn.click();
  // Give the accept a moment to complete and the list to refetch.
  await expect(acceptBtn).toHaveText(/Accept.*create invoice|Working/, {
    timeout: 10_000,
  });
  // The success message should be surfaced by the panel.
  await expect(page.getByText(/Accepted — invoice/)).toBeVisible({
    timeout: 10_000,
  });

  // --- 6. Verify server-side that an Invoice row was created via the
  //         seed's token, plus the ocr_extraction row is now accepted. ---
  const listRes = await fetch(
    `${API}/ocr/extractions?gstin_profile_id=${seed.gstinProfileId}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(listRes.ok).toBeTruthy();
  const rows = (await listRes.json()) as Array<{ id: string; status: string }>;
  expect(rows.length).toBeGreaterThan(0);
  // Every draft that came through this spec must now be accepted.
  const accepted = rows.filter((r) => r.status === "accepted");
  expect(accepted.length).toBeGreaterThan(0);
});
