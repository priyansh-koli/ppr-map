/**
 * Against the running stack with real data (`make up`, the pipeline run, `make basemap`):
 * `make e2e-stack`. Not part of CI, which has no data.
 */
import { expect, test } from "@playwright/test";

test("the banner shows how recent the register is", async ({ page }) => {
  await page.goto("./");
  // The header pill (only its dot on phones) opens the full sentence.
  const pill = page.locator("summary", { hasText: /Data to \d+ \w+ \d{4}/ });
  await expect(pill).toBeVisible();
  await pill.click();
  await expect(page.getByText(/Property Price Register data up to \d+ \w+ \d{4}/)).toBeVisible();
});

test("the national map loads sales tiles and the basemap", async ({ page }) => {
  const tiles = page.waitForResponse((r) => r.url().includes("/api/v1/tiles/sales/") && r.ok());
  const basemap = page.waitForResponse(
    (r) => r.url().includes("/basemap/ireland.pmtiles") && r.status() === 206,
  );
  await page.goto("./map");
  await tiles;
  await basemap;
  await expect(page.getByText(/Zoom in to a town/)).toBeVisible();
});

test("the list is a keyboard equivalent of the map", async ({ page }) => {
  await page.goto("./map?lat=53.3321&lng=-6.2711&z=16");
  const list = page.getByRole("region").or(page.locator("section[aria-labelledby=list-heading]"));
  const first = page.locator("section[aria-labelledby=list-heading] li button").first();
  await expect(first).toBeVisible({ timeout: 15_000 });
  const address = (await first.locator("span").first().textContent()) ?? "";
  await first.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Sale details" });
  await expect(dialog.getByText(address)).toBeVisible();
  await expect(dialog.getByText(/€[\d,]+/).first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  expect(list).toBeTruthy();
});

test("details lead to the property page", async ({ page }) => {
  await page.goto("./map?lat=53.3321&lng=-6.2711&z=16");
  const first = page.locator("section[aria-labelledby=list-heading] li button").first();
  await expect(first).toBeVisible({ timeout: 15_000 });
  const address = (await first.locator("span").first().textContent()) ?? "";
  await first.click();
  await page.getByRole("link", { name: /Full sale history/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(address);
  await expect(page.getByRole("heading", { name: "Sales", exact: true })).toBeAttached();
});

test("filters change the list and the address bar", async ({ page }) => {
  await page.goto("./map?lat=53.3321&lng=-6.2711&z=16");
  await expect(page.locator("section[aria-labelledby=list-heading] li button").first()).toBeVisible(
    {
      timeout: 15_000,
    },
  );
  await page.getByLabel("Type").selectOption("new");
  await expect(page).toHaveURL(/type=new/);
  const texts = await page
    .locator("section[aria-labelledby=list-heading] li button")
    .allTextContents();
  for (const t of texts) expect(t).toContain("new");
});

test("a sale chosen in the list is selected on the map and in the list", async ({ page }) => {
  await page.goto("./map?lat=53.3321&lng=-6.2711&z=16");
  const first = page.locator("section[aria-labelledby=list-heading] li button").first();
  await expect(first).toBeVisible({ timeout: 15_000 });
  const address = (await first.locator("span").first().textContent()) ?? "";
  await first.click();
  const current = page.locator("section[aria-labelledby=list-heading] [aria-current=true]");
  await expect(current).toHaveCount(1);
  await expect(current).toContainText(address);
  await page.keyboard.press("Escape");
  await expect(current).toHaveCount(0);
});

test("clicking empty map closes a pinned sale", async ({ page }) => {
  // Strand Road, Sandymount: houses to the west, the strand and the sea to the east.
  await page.goto("./map?lat=53.3262&lng=-6.2135&z=16");
  const first = page.locator("section[aria-labelledby=list-heading] li button").first();
  await expect(first).toBeVisible({ timeout: 15_000 });
  await first.click();
  const dialog = page.getByRole("dialog", { name: "Sale details" });
  await expect(dialog).toBeVisible();
  const map = page.getByRole("region", { name: "Map of property sales" });
  const box = await map.boundingBox();
  if (!box) throw new Error("the map has no size");
  await page.waitForTimeout(1000); // the map eases to the chosen sale first
  await map.click({ position: { x: box.width - 30, y: box.height / 2 } });
  await expect(dialog).toBeHidden();
  await expect(
    page.locator("section[aria-labelledby=list-heading] [aria-current=true]"),
  ).toHaveCount(0);
});

test("the 3D view tilts the map over its terrain and lays it flat again", async ({ page }) => {
  const terrain = page.waitForResponse(
    (r) => r.url().includes("/basemap/terrain.pmtiles") && r.status() === 206,
  );
  await page.goto("./map?lat=53.3455&lng=-6.238&z=16");
  await terrain; // the relief is shaded in the flat view too
  const button = page.getByRole("button", { name: "3D view" });
  await expect(button).toBeEnabled({ timeout: 15_000 });
  await expect(button).toHaveAttribute("aria-pressed", "false");
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(/pitch=60/);
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "false");
  await expect(page).not.toHaveURL(/pitch=/);
});
