import { test, expect } from '@playwright/test';
import { setupBaseMocks, mockApiRoute } from './helpers';

test.describe('E2E: Focus / Campaigns', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('navigates to Focus tab', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Focus' }).first().click();

    await expect(page.getByText(/Focus & Campanii/i)).toBeVisible({ timeout: 10000 });
  });

  test('Focus tab renders campaign section', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Focus' }).first().click();

    await expect(page.getByText(/Campanii/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('Focus tab with promo data shows title', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/api\/campaigns\/promotions-incentives/, {
      has_active_promotion: true,
      promo_title: 'Promo Mai 2026',
      promo_total_qty: 150,
      promo_category_qty: 0,
      top_stores: [],
      top_agents: [],
      incentive_title: null,
      incentive_categories: [],
      incentive_product_count: 0,
    });

    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Focus' }).first().click();

    await expect(page.getByText(/Campanii/i).first()).toBeVisible({ timeout: 10000 });
  });
});
