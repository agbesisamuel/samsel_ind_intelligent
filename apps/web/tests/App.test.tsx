/** Protect honest missing-data states, localization, and unavailable auth routes. */
import { beforeEach, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "../src/app/App";
import { LocaleProvider } from "../src/i18n/LocaleProvider";
import { fetchHealth } from "../src/api/client";
import en from "../src/i18n/en.json";
import da from "../src/i18n/da.json";
import { api, ApiFailure, collection } from "../src/api/identity";
import { identityMessages } from "../src/app/identityMessages";
import { inventoryMessages } from "../src/app/inventoryMessages";
import { csvHeaders, readingValue } from "../src/app/Monitoring";
import { ruleStage } from "../src/app/Rules";
import { notificationHealth } from "../src/app/Notifications";
import {
  evidenceText,
  incidentEventTitle,
  incidentState,
} from "../src/app/Incidents";

vi.mock("../src/api/client", () => ({ fetchHealth: vi.fn() }));

test("anonymous pilot routes issue no tenant metadata queries", async () => {
  vi.mocked(collection).mockClear();
  renderApp("/integrations");
  expect(
    await screen.findByRole("link", { name: /Sign in to access/ }),
  ).toBeInTheDocument();
  expect(collection).not.toHaveBeenCalled();
});
vi.mock("../src/api/identity", async (original) => ({
  ...(await original<typeof import("../src/api/identity")>()),
  api: vi.fn(),
  collection: vi.fn(),
}));
beforeEach(() => {
  localStorage.clear();
  vi.mocked(fetchHealth).mockResolvedValue(true);
  vi.mocked(api).mockRejectedValue(new ApiFailure(403));
});

/** Isolate the query cache and router for each scenario. */
function renderApp(path = "/") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <LocaleProvider>
          <App />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("process success never fabricates healthy readings", async () => {
  renderApp();
  expect(await screen.findByText("API reachable")).toBeInTheDocument();
  expect(screen.getByText("No live site monitoring")).toBeInTheDocument();
  expect(screen.queryByText(/0°C/)).not.toBeInTheDocument();
});
test("network failure is explicit and retryable", async () => {
  vi.mocked(fetchHealth).mockRejectedValue(new Error("offline"));
  renderApp();
  expect(await screen.findByText("API unavailable")).toBeInTheDocument();
  vi.mocked(fetchHealth).mockResolvedValue(true);
  await userEvent.click(screen.getByRole("button", { name: "Check again" }));
  expect(await screen.findByText("API reachable")).toBeInTheDocument();
});
test("Danish switch translates navigation and persists language only", async () => {
  renderApp();
  await userEvent.selectOptions(screen.getByLabelText("Language"), "da");
  expect(
    screen.getByRole("navigation", { name: "Hovednavigation" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Ingen live-overvågning")).toBeInTheDocument();
  expect(document.documentElement.lang).toBe("da");
  expect(Object.keys(localStorage)).toEqual(["sii.locale"]);
  expect(Object.keys(da).sort()).toEqual(Object.keys(en).sort());
});
test("signed-out administration hides customer records and directs to sign-in", async () => {
  renderApp("/users");
  expect(
    await screen.findByRole("heading", { name: "Invite user" }),
  ).toBeInTheDocument();
  expect(screen.getByText(en.authUnavailable)).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

test("password login progresses to MFA without storing secrets", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith("login/")) return { state: "mfa" };
    throw new ApiFailure(403);
  });
  renderApp("/login");
  await userEvent.type(screen.getByLabelText("Email"), "owner@example.invalid");
  await userEvent.type(
    screen.getByLabelText("Password"),
    "test password proof",
  );
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(
    await screen.findByLabelText("Authenticator or recovery code"),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  expect(Object.keys(localStorage)).toEqual(["sii.locale"]);
});

test("identity dictionaries include every recovery and administration message", () => {
  expect(Object.keys(identityMessages.en).sort()).toEqual(
    Object.keys(identityMessages.da).sort(),
  );
});

test("MFA enrollment shows recovery codes only after successful verification", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith("login/")) return { state: "enroll" };
    if (path.endsWith("enroll/"))
      return { state: "enroll", secret: "synthetic-display-only" };
    if (path.endsWith("verify/"))
      return { state: "complete", recovery_codes: ["synthetic-one-time-code"] };
    throw new ApiFailure(403);
  });
  renderApp("/login");
  await userEvent.type(screen.getByLabelText("Email"), "owner@example.invalid");
  await userEvent.type(
    screen.getByLabelText("Password"),
    "test password proof",
  );
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText("synthetic-display-only")).toBeInTheDocument();
  await userEvent.type(
    screen.getByLabelText("Authenticator or recovery code"),
    "123456",
  );
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
  expect(
    await screen.findByText("synthetic-one-time-code"),
  ).toBeInTheDocument();
  expect(screen.queryByText("synthetic-display-only")).not.toBeInTheDocument();
});
test("inventory dictionaries cover every qualification warning in both languages", () => {
  expect(Object.keys(inventoryMessages.en).sort()).toEqual(
    Object.keys(inventoryMessages.da).sort(),
  );
});

test("unknown routes provide a way back", () => {
  renderApp("/does-not-exist");
  expect(
    screen.getByRole("heading", { name: "Page not found" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Return to overview" }),
  ).toHaveAttribute("href", "/");
});

test("monitoring displays zero independently from missing data and parses quoted CSV columns", () => {
  expect(readingValue("0.0000", "en")).toBe("0");
  expect(readingValue(null, "en")).toBe("—");
  expect(readingValue("1.25", "da")).toBe("1,25");
  expect(csvHeaders('"probe,name",time,"value"\nignored,data,rows')).toEqual([
    "probe,name",
    "time",
    "value",
  ]);
});

test("rule lifecycle labels retain synthetic and superseded provenance in both languages", () => {
  expect(ruleStage("active_synthetic", "en")).toContain("synthetic");
  expect(ruleStage("active_synthetic", "da")).toContain("syntetisk");
  expect(ruleStage("superseded", "en")).toBe("Superseded");
  expect(ruleStage("approved", "da")).toBe("QA-godkendt");
});

test("notification health never treats missing worker evidence as running", () => {
  expect(notificationHealth("unknown_or_delayed", "en")).toBe(
    "Unknown or delayed",
  );
  expect(notificationHealth("", "da")).toBe("Ukendt eller forsinket");
  expect(notificationHealth("running", "en")).toBe("Running");
});

test("incident evidence keeps recovery distinct from closure and validates untyped text", () => {
  expect(incidentEventTitle("incident.recovered.v1", "en")).toBe(
    "Recovery observed",
  );
  expect(incidentState("closed", "da")).toBe("Lukket");
  expect(evidenceText({ text: { unexpected: true } }, "text")).toBeUndefined();
  expect(evidenceText(null, "text")).toBeUndefined();
  expect(evidenceText({ text: "Human note" }, "text")).toBe("Human note");
});
