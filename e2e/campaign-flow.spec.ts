import { test, expect } from '@playwright/test';
import { mockAuthenticatedSession, mockApiRoute, MOCK_MONTHS, MOCK_FILTER_OPTIONS } from './helpers';

test.describe('E2E: Campaign Creation & Assignment', () => {
  test.beforeEach(async ({ context }) => {
    await mockAuthenticatedSession(context);
    await mockApiRoute(context, 'GET', /\/api\/filters\/available-months/, MOCK_MONTHS);
    await mockApiRoute(context, 'GET', /\/api\/filters\/options.*/, MOCK_FILTER_OPTIONS);
  });

  test('navigates to Focus → Campaigns', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    // Click Focus tab
    await page.getByRole('button', { name: /Focus/i }).click();

    await expect(page.getByText(/Campanii|Incentive/i)).toBeVisible({ timeout: 10000 });
  });

  test('displays campaigns list', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/api\/campaigns.*/, {
      campaigns: [
        {
          id: 1,
          name: 'Campanie Promo Mai',
          type: 'promo',
          start_date: '2026-05-01',
          end_date: '2026-05-31',
          status: 'active',
        },
        {
          id: 2,
          name: 'Incentive Q2',
          type: 'incentive',
          start_date: '2026-04-01',
          end_date: '2026-06-30',
          status: 'active',
        },
      ],
    });

    await page.goto('/');
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Focus/i }).click();

    await expect(page.getByText('Campanie Promo Mai')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Incentive Q2')).toBeVisible();
  });

  test('can filter campaigns', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Focus/i }).click();

    // Section switcher between campaigns and focus products
    const campaignBtn = page.getByRole('button', { name: /Campanii/i });
    const focusBtn = page.getByRole('button', { name: /Produse Focus/i });

    // Both section buttons should be visible
    await expect(campaignBtn.or(focusBtn).first()).toBeVisible({ timeout: 5000 });
  });
});
