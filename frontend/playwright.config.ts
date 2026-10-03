import { defineConfig, devices } from "@playwright/test";

const PORT = 3000;

// E2E_STATIC=1 tests the static export in `out/` as Vercel serves the preview (make e2e-static).
// On CI otherwise, the standalone server the Docker image runs; locally, `next dev`.
const STATIC = process.env.E2E_STATIC === "1";
// E2E_STACK=1 runs e2e-stack/ against the Docker stack with real data (make e2e-stack).
const STACK = process.env.E2E_STACK === "1";

function serverCommand(): string {
  if (STATIC) return "node e2e/serve-export.mjs";
  return process.env.CI ? "npm run start:standalone" : "npm run dev";
}

export default defineConfig({
  testDir: STACK ? "./e2e-stack" : "./e2e",
  globalSetup: STACK ? "./e2e-stack/global-setup.ts" : undefined,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Specs navigate relative to the base URL (`./map`).
  use: {
    baseURL: STACK ? "http://localhost:8080/" : `http://localhost:${PORT}/`,
    trace: "on-first-retry",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: STACK
    ? undefined
    : {
        command: serverCommand(),
        port: PORT,
        env: { PORT: String(PORT) },
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
