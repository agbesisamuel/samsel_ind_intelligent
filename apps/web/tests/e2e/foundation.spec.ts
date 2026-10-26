/** Real-browser acceptance: API proxy, bilingual shell, deep links and narrow layout. */
import { test, expect } from "@playwright/test";

test("local foundation is reachable and honest in both languages", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("API reachable")).toBeVisible();
  await expect(page.getByText("No live site monitoring")).toBeVisible();
  await page.screenshot({
    path: "../../output/playwright/overview-en.png",
    fullPage: true,
  });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.getByLabel("Language").selectOption("da");
  await expect(page.getByText("Ingen live-overvågning")).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "da");
  await page.goto("/users");
  await expect(
    page.getByRole("heading", { name: "Invitér bruger" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Log ind for at se dine tilladte organisationer og lokationer.",
    ),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/users-da-mobile.png",
    fullPage: true,
  });
});
