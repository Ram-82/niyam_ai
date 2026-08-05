/**
 * Design-review screenshots. NOT a functional smoke — it just logs
 * in with the demo firm's credentials, walks the key screens, and
 * writes PNGs to ``e2e/screenshots/`` for inclusion in a
 * design-pass report.
 *
 * Assumes the demo firm exists (run
 * ``docker compose run --rm backend python -m scripts.seed_demo``
 * first). If it doesn't, the test skips (there's nothing to shoot).
 */
import { test, expect } from "@playwright/test";
import { authenticator } from "otplib";
import { mkdirSync } from "node:fs";


const EMAIL = "demo@niyam.ai";
const PASSWORD = "DemoPassword-2026-Correct";
const TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";
const OUT_DIR = "e2e/screenshots";

mkdirSync(OUT_DIR, { recursive: true });


test.describe("design screens (demo firm)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("capture key screens", async ({ page }) => {
    // --- Login ---
    await page.goto("/login");
    await page.screenshot({ path: `${OUT_DIR}/01-login.png`, fullPage: true });

    await page.getByTestId("login-email").fill(EMAIL);
    await page.getByTestId("login-password").fill(PASSWORD);
    await page.getByTestId("login-totp").fill(authenticator.generate(TOTP_SECRET));
    await page.getByTestId("login-submit").click();

    // If the demo firm isn't seeded, login fails — skip cleanly.
    try {
      await expect(page).toHaveURL(/\/command-center/, { timeout: 5_000 });
    } catch {
      test.skip(true, "demo firm not seeded — run seed_demo and retry");
      return;
    }

    // --- Command center ---
    // PeriodNav is now a button, not a text input. The default resolves
    // to last-completed-month, which matches the seed's period.
    await page.waitForTimeout(600);   // let fetch resolve
    await expect(page.getByTestId("cc-row").first()).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: `${OUT_DIR}/02-command-center.png`, fullPage: true });

    // --- Workspace: reconciliation tab, supplier_default bucket ---
    await page.getByTestId("cc-drill").first().click();
    await expect(page).toHaveURL(/\/workspace\//);
    await page.getByTestId("tab-reconciliation").click();
    await page.getByTestId("bucket-supplier_default").click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT_DIR}/03-recon-supplier-default.png`, fullPage: true });

    // --- Workspace: returns tab, arithmetic drawer open ---
    await page.getByTestId("tab-returns").click();
    await page.waitForTimeout(300);
    const score = page.getByTestId("score-value").or(page.getByTestId("score-badge"));
    if (await score.count() > 0) {
      await score.first().click();
      await page.waitForTimeout(200);
      await page.screenshot({ path: `${OUT_DIR}/04-returns-arithmetic.png`, fullPage: true });
    }

    // --- Empty-state: step back 11 months via the PeriodNav prev
    // chevron (dropdown only shows 12 trailing months; hopping further
    // needs the chevron). Any period without a scoring run renders
    // NULL scores as "Not yet scored" — that's the empty-ish state.
    await page.goto("/command-center");
    await page.waitForTimeout(500);
    for (let i = 0; i < 11; i++) {
      await page.getByRole("button", { name: "Previous month" }).click();
      await page.waitForTimeout(50);
    }
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT_DIR}/05-not-yet-scored.png`, fullPage: true });
  });
});
