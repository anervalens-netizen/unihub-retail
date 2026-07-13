import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { outputFolder: 'playwright-report' }], ['list']],
  timeout: 30000,
  expect: { timeout: 10000 },

  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3333',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      command: process.env.CI
        ? 'npx vite preview --port 3333 --host 0.0.0.0'
        : 'npm run build && npx vite preview --port 3333 --host 0.0.0.0',
      url: 'http://localhost:3333',
      // The test run must own the preview lifecycle. Reusing a preview from
      // an interrupted run can make it disappear while parallel tests run.
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
