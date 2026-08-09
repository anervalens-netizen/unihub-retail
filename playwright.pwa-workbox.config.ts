import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'pwa-release-lifecycle.spec.ts',
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report-pwa-workbox' }], ['list']],
  outputDir: 'test-results/pwa-workbox',
  timeout: 30_000,
  use: {
    ...devices['Desktop Chrome'],
    serviceWorkers: 'allow',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
