// @ts-check
const { defineConfig, devices } = require('@playwright/test');

/**
 * Playwright configuration for Demo UI browser tests.
 * Uses API fixtures to isolate frontend testing from full backend dependencies.
 * @see PHASE 2 Task 2.3: BROWSER_WITH_API_FIXTURES
 */
module.exports = defineConfig({
  testDir: './frontend/tests',
  timeout: 30000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: process.env.SKIP_WEB_SERVER ? undefined : {
    command: 'python -m uvicorn backend.app.main:app --port 8000 --host 0.0.0.0',
    url: 'http://localhost:8000/demo',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
