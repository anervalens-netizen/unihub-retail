import { test, expect } from './fixtures';
import { setupBaseMocks, mockApiRoute } from './helpers';

test.describe('E2E: Excel Import (Settings)', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('navigates to Settings and shows import heading', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).first().click();

    await expect(page.getByRole('heading', { name: /Import fișier/i })).toBeVisible({ timeout: 10000 });
  });

  test('shows import button', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).first().click();

    await expect(page.getByText(/Importă fișier/i)).toBeVisible({ timeout: 10000 });
  });

  test('renders import history entries', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/api\/import\/history/, [
      {
        import_month: '2026-05',
        filename: 'vanzari_mai.xlsx',
        status: 'completed',
        rows_imported: 250,
        coverage_report: {
          active_store_coverage_pct: 90,
          missing_active_store_count: 3,
        },
        created_at: '2026-05-06T10:00:00',
      },
    ]);

    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).first().click();

    await expect(page.getByText('vanzari_mai.xlsx')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Coverage magazine active 90%.*3 absente/)).toBeVisible();
  });
});
