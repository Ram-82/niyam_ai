import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: {
    // Unit tests only. Playwright specs live under e2e/ and MUST be
    // excluded — vitest's default include pattern (*.spec.ts) matches
    // them otherwise, which tries to run Playwright's test.beforeAll()
    // in vitest's runner and blows up.
    include: ["lib/**/*.test.ts"],
    exclude: ["e2e/**", "node_modules/**", ".next/**", "dist/**"],
    environment: "node",
  },
  resolve: {
    alias: {
      "@": here,
    },
  },
});
