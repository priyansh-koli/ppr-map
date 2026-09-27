import { expect, test } from "@playwright/test";

import { PSRA_ATTRIBUTION } from "../src/lib/attribution";
import { ROUTES } from "../src/lib/routes";

const BASE_PATH = process.env.E2E_BASE_PATH ?? "";

for (const [key, route] of Object.entries(ROUTES)) {
  test(`${key} renders (${route.samplePath})`, async ({ page }) => {
    const response = await page.goto(`.${route.samplePath}`);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(route.title);
    await expect(page.getByText(PSRA_ATTRIBUTION)).toBeVisible();
  });
}

test("internal links stay under the base path", async ({ page }) => {
  await page.goto("./");
  const hrefs = await page
    .locator('a[href^="/"]')
    .evaluateAll((links) => links.map((a) => a.getAttribute("href") ?? ""));
  expect(hrefs.length).toBeGreaterThan(0);
  for (const href of hrefs) expect(href.startsWith(`${BASE_PATH}/`), href).toBe(true);
});

test("skip link moves keyboard focus to main content", async ({ page }) => {
  await page.goto("./");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});
