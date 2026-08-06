import { test, expect } from './fixtures';
import { setupBaseMocks, mockApiRoute } from './helpers';
import type { ImportHistoryEntry } from '../src/api/generated/runtime-types';

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

    await expect(
      page.getByRole('button', { name: /Validează fișierul/i }),
    ).toBeVisible({ timeout: 10000 });
  });

  test('renders import history entries', async ({ page, context }) => {
    const history: ImportHistoryEntry[] = [
      {
        id: 205,
        import_month: '2026-05',
        filename: 'vanzari_mai.xlsx',
        upload_date: '2026-05-06',
        status: 'completed',
        rows_in_file: 250,
        rows_imported: 250,
        is_month_final: true,
        error_message: null,
        finished_at: '2026-05-06T10:00:12Z',
        duration_seconds: 12,
        coverage_report: {
          active_store_count_before: 100,
          active_store_coverage_pct: 90,
          company_count: 2,
          incoming_store_count: 90,
          metadata_change_count: 0,
          missing_active_store_count: 3,
          missing_prior_store_count: 0,
          new_store_count: 0,
          prior_snapshot_coverage_pct: 100,
          prior_snapshot_store_count: 90,
          store_activity_writes: 0,
        },
        created_at: '2026-05-06T10:00:00Z',
      },
    ];
    await mockApiRoute(context, 'GET', /\/api\/import\/history/, history);

    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).first().click();

    await expect(page.getByText('vanzari_mai.xlsx')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Coverage magazine active 90%.*3 absente/)).toBeVisible();
  });
});
