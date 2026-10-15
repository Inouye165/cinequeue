import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.e2e.ts",
  fullyParallel: true,
  use: {
    baseURL: "http://localhost:5180",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run build && npm run preview -- --port 5180 --strictPort",
    url: "http://localhost:5180",
    reuseExistingServer: false,
    timeout: 120000,
  },
});
