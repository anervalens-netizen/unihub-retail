import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'ai-assistant-responsive.spec.ts',
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  outputDir: 'test-results/ai-responsive',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.REAL_E2E_BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
