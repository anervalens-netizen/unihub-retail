import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: ['login-dashboard.spec.ts', 'browser-keyboard-smoke.spec.ts'],
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
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: {
    command: 'npx vite preview --port 3334 --host 127.0.0.1',
    url: 'http://127.0.0.1:3334',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
