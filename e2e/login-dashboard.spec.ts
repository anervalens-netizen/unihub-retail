import { test, expect } from '@playwright/test';
import {
  mockAuthenticatedSession,
  mockApiRoute,
  MOCK_MONTHS,
  MOCK_FILTER_OPTIONS,
  MOCK_DASHBOARD_ALL,
  MOCK_DASHBOARD_HISTORY,
  MOCK_DASHBOARD_YEAR_HISTORY,
} from './helpers';

test.describe('E2E: Login → Dashboard', () => {
  test.beforeEach(async ({ context }) => {
    await mockAuthenticatedSession(context);
    await mockApiRoute(context, 'GET', /\/api\/filters\/available-months/, MOCK_MONTHS);
    await mockApiRoute(context, 'GET', /\/api\/filters\/options.*/, MOCK_FILTER_OPTIONS);
    await mockApiRoute(context, 'GET', /\/api\/dashboard\/all.*/, MOCK_DASHBOARD_ALL);
    await mockApiRoute(context, 'GET', /\/api\/dashboard\/history.*/, MOCK_DASHBOARD_HISTORY);
    await mockApiRoute(context, 'GET', /\/api\/dashboard\/history-year.*/, MOCK_DASHBOARD_YEAR_HISTORY);
  });

  test('renders dashboard after authenticated session', async ({ page }) => {
    await page.goto('/');

    // Auth context should make the app render MainLayout, not login screen
    await expect(page.getByText('Nu ești autentificat.')).toHaveCount(0);

    // Dashboard tabs should be visible
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Focus')).toBeVisible();
    await expect(page.getByText('Agenti')).toBeVisible();
  });

  test('shows dashboard summary cards', async ({ page }) => {
    await page.goto('/');

    // Wait for the dashboard to load
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    // Summary data should appear (mocked values)
    await expect(page.getByText('150.000')).toBeVisible({ timeout: 10000 });
  });

  test('navigates between tabs', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    // Click Focus tab
    await page.getByText('Focus').click();
    await expect(page.getByText('Campanii')).toBeVisible({ timeout: 5000 });

    // Click Agenti tab
    await page.getByText('Agenti').click();
    await expect(page.locator('text=Agenti')).toBeVisible({ timeout: 5000 });
  });

  test('shows filter panel', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    // Open filter panel
    const filterButton = page.locator('button').filter({ has: page.locator('svg') }).first();
    await filterButton.click();

    // Filters should render
    await expect(page.getByText(/Firma|Regional|ASM|Magazin/)).toBeVisible({ timeout: 5000 });
  });
});
