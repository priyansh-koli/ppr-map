import { defineConfig, devices } from "@playwright/test";

const PORT = 3000;

// E2E_BASE_PATH (e.g. `/ppr-map`) tests the static export in `out/` as GitHub Pages serves it.
// On CI otherwise, the standalone server the Docker image runs; locally, `next dev`.
const BASE_PATH = process.env.E2E_BASE_PATH;

function serverCommand(): string {
  if (BASE_PATH !== undefined) return "node e2e/serve-export.mjs";
  return process.env.CI ? "npm run start:standalone" : "npm run dev";
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Trailing slash: specs navigate relative to it (`./map`), so the base path is kept.
  use: { baseURL: `http://localhost:${PORT}${BASE_PATH ?? ""}/`, trace: "on-first-retry" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: serverCommand(),
    port: PORT,
    env: { PORT: String(PORT), BASE_PATH: BASE_PATH ?? "" },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
