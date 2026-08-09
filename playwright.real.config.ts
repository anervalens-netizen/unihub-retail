import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'real-auth-stack.spec.ts',
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report-real' }], ['list']],
  outputDir: 'test-results/real-e2e',
  timeout: 45_000,
  expect: { timeout: 15_000 },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.REAL_E2E_BASE_URL,
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
