import { expect, test } from "@playwright/test";

import { PSRA_ATTRIBUTION } from "../src/lib/attribution";
import { ROUTES } from "../src/lib/routes";

for (const [key, route] of Object.entries(ROUTES)) {
  test(`${key} renders (${route.samplePath})`, async ({ page }) => {
    const response = await page.goto(`.${route.samplePath}`);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(route.title);
    await expect(page.getByText(PSRA_ATTRIBUTION)).toBeVisible();
  });
}

test("skip link moves keyboard focus to main content", async ({ page }) => {
  await page.goto("./");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});
