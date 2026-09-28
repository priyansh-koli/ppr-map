/**
 * Accounts through the browser, against the running stack, with the real emails read from
 * Mailpit (http://localhost:8025). `make e2e-stack`.
 */
import { expect, type Page, test } from "@playwright/test";

const MAILPIT = "http://localhost:8025/api/v1";
const PASSWORD = "correct horse battery staple";

async function linkFromEmail(page: Page, to: string, path: string): Promise<string> {
  for (let i = 0; i < 20; i++) {
    const search = await page.request.get(
      `${MAILPIT}/search?query=${encodeURIComponent(`to:${to}`)}`,
    );
    const { messages } = (await search.json()) as { messages: { ID: string }[] };
    for (const m of messages) {
      const msg = (await (await page.request.get(`${MAILPIT}/message/${m.ID}`)).json()) as {
        Text: string;
      };
      const match = msg.Text.match(new RegExp(`https?://\\S+${path}\\?token=[\\w-]+`));
      if (match) return new URL(match[0]).pathname + new URL(match[0]).search;
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`no ${path} email for ${to}`);
}

/** On phones the account links sit in the header's menu sheet. */
async function openMenuOnPhones(page: Page) {
  const menu = page.getByRole("button", { name: "Menu" });
  if (await menu.isVisible()) await menu.click();
}

test("register, confirm, sign in, save, compare, history, sign out", async ({ page }, info) => {
  const email = `e2e-${info.project.name}-${Date.now()}@example.ie`;

  await page.goto("./register");
  await page.getByLabel("Name", { exact: true }).fill("Aoife Byrne");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("I am 18 or older.").check();
  await page.getByLabel(/I accept the/).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Check your email to continue.")).toBeVisible();

  await page.goto(`.${await linkFromEmail(page, email, "/verify-email")}`);
  await expect(page.getByText("Your email is confirmed.")).toBeVisible();

  await page.goto("./login?next=/account");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await expect(page.getByText("Your email is confirmed.")).toBeVisible();

  // Save two properties from their pages; visiting them also records history.
  const list = (await (
    await page.request.get("./api/v1/properties?bbox=-6.2725,53.3315,-6.2700,53.3330&pageSize=2")
  ).json()) as { items: { id: string; address: string }[] };
  for (const item of list.items) {
    await page.goto(`./property/${item.id}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(item.address);
    await page.getByRole("button", { name: "Save to wishlist" }).click();
    await expect(page.getByText("Saved.")).toBeVisible();
  }

  await page.goto("./account/wishlist");
  for (const item of list.items) {
    await page.getByLabel(`Compare ${item.address}`).check();
  }
  await page.getByRole("link", { name: "Compare 2" }).click();
  for (const item of list.items) {
    await expect(page.getByRole("columnheader", { name: item.address })).toBeVisible();
  }

  await page.goto("./account/history");
  for (const item of list.items) {
    await expect(page.getByRole("link", { name: item.address })).toBeVisible();
  }

  await openMenuOnPhones(page);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/$/); // signing out goes home, which closes the menu
  await openMenuOnPhones(page);
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await page.goto("./account/wishlist");
  await expect(page.getByText("to continue.")).toBeVisible();
});

test("password reset by email", async ({ page }, info) => {
  const email = `e2e-reset-${info.project.name}-${Date.now()}@example.ie`;
  await page.goto("./register");
  await page.getByLabel("Name", { exact: true }).fill("Seán Ó Dálaigh");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("I am 18 or older.").check();
  await page.getByLabel(/I accept the/).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Check your email to continue.")).toBeVisible();

  await page.goto("./forgot-password");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Email me a reset link" }).click();
  await expect(page.getByText(/a reset link is on its way/)).toBeVisible();

  await page.goto(`.${await linkFromEmail(page, email, "/reset-password")}`);
  const fresh = "a brand new long passphrase";
  await page.getByLabel("New password", { exact: true }).fill(fresh);
  await page.getByLabel("New password again").fill(fresh);
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByText(/Your password is changed/)).toBeVisible();

  await page.goto("./login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(fresh);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
  await openMenuOnPhones(page);
  await expect(page.getByRole("link", { name: "Account" })).toBeVisible();
});
