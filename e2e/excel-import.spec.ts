import { test, expect } from '@playwright/test';
import { mockAuthenticatedSession, mockApiRoute, MOCK_MONTHS, MOCK_FILTER_OPTIONS } from './helpers';

test.describe('E2E: Excel Salary Import', () => {
  test.beforeEach(async ({ context }) => {
    await mockAuthenticatedSession(context);
    await mockApiRoute(context, 'GET', /\/api\/filters\/available-months/, MOCK_MONTHS);
    await mockApiRoute(context, 'GET', /\/api\/filters\/options.*/, MOCK_FILTER_OPTIONS);
  });

  test('navigates to Settings → Import', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    // Navigate to Settings tab
    await page.getByRole('button', { name: /Setari/i }).click();

    // Should show import section
    await expect(page.getByText(/Import|Incarca/i)).toBeVisible({ timeout: 10000 });
  });

  test('shows import form for salary Excel', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).click();

    // File input should be available for Excel upload
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeVisible({ timeout: 10000 });
  });

  test('shows import history after upload', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/api\/imports.*/, {
      imports: [
        {
          id: 1,
          import_month: '2026-05',
          filename: 'salarii_mai.xlsx',
          status: 'completed',
          rows_imported: 250,
          import_type: 'salarii',
        },
      ],
    });

    await page.goto('/');
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).click();

    await expect(page.getByText('salarii_mai.xlsx')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('completed')).toBeVisible();
  });
});
