import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'frontend-lifecycle.spec.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report-browser-smoke' }], ['list']],
  outputDir: 'test-results/browser-smoke',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:3334',
    serviceWorkers: 'block',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      grep: /\.(?:allowed|denied|401_redirect_once|403_safe|409_retry|keyboard|mobile)$/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      grep: /\.(?:success|401_redirect_once|keyboard)$/,
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      grep: /\.(?:success|401_redirect_once|keyboard)$/,
      use: { ...devices['Desktop Safari'] },
    },
  ],
  webServer: {
    command: 'node_modules/.bin/vite preview --port 3334 --host 127.0.0.1',
    url: 'http://127.0.0.1:3334',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
