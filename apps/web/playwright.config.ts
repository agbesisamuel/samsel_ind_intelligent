/** Browser smoke runs against the actual Compose stack, never a mocked API. */
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173" },
  reporter: "list",
  retries: 0,
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
