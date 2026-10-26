/** Local SPA server: API stays same-origin through a proxy; no permissive CORS. */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Docker Desktop bind mounts can miss Windows file events; poll only when requested.
    watch: {
      usePolling: process.env.SII_WATCH_POLLING === "true",
      interval: 500,
    },
    proxy: { "/api": process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.tsx"],
  },
});
