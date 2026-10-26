/** Actual session/cookie acceptance using only the guarded local synthetic operator fixture. */
import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

test("operator sees only A1, cannot manage identities, and logout revokes access", async ({
  page,
}) => {
  // Read only this local generated credential; never print it or attach authentication traces.
  const config = readFileSync(
    new URL("../../../../.env", import.meta.url),
    "utf8",
  );
  const password = config.match(/^DEMO_OPERATOR_PASSWORD=(.+)$/m)?.[1].trim();
  if (!password)
    throw new Error("Run setup and seed-demo before browser tests");
  await page.goto("/login");
  await page
    .getByLabel("Email", { exact: true })
    .fill("operator@example.invalid");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Fictional site A1" }),
  ).toBeVisible();
  await expect(page.getByText("Fictional site A2")).toHaveCount(0);
  await expect(page.getByText("Fictional site B1")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Users & permissions" }),
  ).toHaveCount(0);
  // Planned inventory is visible; unknown calibration and blocked activation stay explicit.
  await page
    .getByRole("link", { name: "Cold rooms & sensors", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Synthetic temperature probe" }),
  ).toBeVisible();
  await expect(
    page.getByText("Calibration unknown", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Local synthetic environment cannot activate live monitoring",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Retire permanently" }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/inventory-en-mobile.png",
    fullPage: true,
  });
  // Read-only monitoring never grants policy approval or manual import to an operator.
  await page.getByRole("link", { name: "Live readings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Readings and freshness", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Fictional site A1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Timing not approved", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Fictional site A2")).toHaveCount(0);
  await expect(page.getByText("Fictional site B1")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Approve timing", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Import reviewed rows", exact: true }),
  ).toHaveCount(0);
  // The transport acceptance fixture supplies actual raw rows; its graph must render real points.
  await page
    .getByRole("button", { name: "SYNTHETIC transport probe", exact: true })
    .click();
  await expect(page.locator(".series-chart circle").first()).toBeVisible();
  await page.getByText("Inspect raw observations", { exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Next page", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/monitoring-en-mobile.png",
    fullPage: true,
  });
  // Operators may inspect synthetic rule evidence but cannot author or approve it.
  await page.getByRole("link", { name: "Rules", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Rules and incident evidence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Version history" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Fictional site A2", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Fictional site B1", { exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/rules-en-mobile.png",
    fullPage: true,
  });
  // Notification evidence is readable, but an operator cannot administer or test routes.
  await page.getByRole("link", { name: "Notifications", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Delivery health" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Delivery evidence" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create route", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Send TEST", exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/notifications-en-mobile.png",
    fullPage: true,
  });
  // Human response remains separate from automatic recovery; operators have no QA/export controls.
  await page
    .getByRole("link", { name: "Alerts & incidents", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Immutable timeline" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Evidence attachments" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Record action", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("option", { name: "QA close", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Download activity JSON", exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/incidents-en-mobile.png",
    fullPage: true,
  });
  // Export controls remain hidden for an operator; a direct route must also deny them.
  await expect(
    page.getByRole("link", { name: "Reports", exact: true }),
  ).toHaveCount(0);
  await page.goto("/reports");
  await expect(
    page.getByText("Your role does not permit exports."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Create report" })).toHaveCount(
    0,
  );
  // Synthetic preparation remains explicitly blocked in both interface languages.
  await page.goto("/integrations");
  await expect(
    page.getByRole("heading", { name: "Integration and pilot preparation" }),
  ).toBeVisible();
  await expect(
    page.getByText("BLOCKED: no authorised hardware/site", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("da");
  await expect(
    page.getByText("BLOKERET: intet godkendt udstyr eller anlæg", {
      exact: true,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../output/playwright/integrations-da-mobile.png",
    fullPage: true,
  });
  // A synthetic support request exercises real scope/CSRF and cannot resolve a safety incident.
  await page.goto("/help");
  await expect(
    page.getByRole("heading", { name: "Hjælp, onboarding og driftsstatus" }),
  ).toBeVisible();
  await expect(
    page.getByText("Produktion er blokeret.", { exact: false }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../../output/playwright/help-da-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("combobox", { name: "Sprog", exact: true })
    .selectOption("en");
  const subject = `SYNTHETIC browser training ${Date.now()}`;
  await page
    .getByRole("textbox", { name: "Subject", exact: true })
    .fill(subject);
  await page
    .getByRole("textbox", { name: "Description", exact: true })
    .fill("SYNTHETIC local training question, no customer data.");
  await page
    .getByRole("button", { name: "Create support request", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: subject, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Reply", exact: true })
    .fill("SYNTHETIC exercise completed; no safety incident changed.");
  await page
    .getByRole("combobox", { name: "Support state", exact: true })
    .selectOption("resolved");
  await page.getByRole("button", { name: "Save reply", exact: true }).click();
  await expect(
    page.getByRole("button", { name: subject, exact: true }).locator(".."),
  ).toContainText("Resolved");
  await page.goto("/billing");
  await expect(
    page.getByText(
      "Only organisation owners and commercial administrators can view billing.",
    ),
  ).toBeVisible();
  const cookie = (await page.context().cookies()).find(
    // Cookie flags remain independent from client-side capability visibility.
    (cookie) => cookie.name === "sessionid",
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  const response = await page.request.post("/api/v1/auth/logout/", {
    data: {},
  });
  expect(response.status()).toBe(403); // Unsafe methods require CSRF even with a valid cookie.
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect((await page.request.get("/api/v1/me/")).status()).toBe(403);
  await page.goto("/sites");
  await expect(
    page.getByText("Sign in to access your permitted organisations and sites."),
  ).toBeVisible();
});
