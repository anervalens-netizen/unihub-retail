import { test, expect } from '@playwright/test';
import { mockAuthenticatedSession, mockApiRoute, MOCK_MONTHS, MOCK_FILTER_OPTIONS } from './helpers';

test.describe('E2E: Store Management', () => {
  test.beforeEach(async ({ context }) => {
    await mockAuthenticatedSession(context);
    await mockApiRoute(context, 'GET', /\/api\/filters\/available-months/, MOCK_MONTHS);
    await mockApiRoute(context, 'GET', /\/api\/filters\/options.*/, MOCK_FILTER_OPTIONS);
  });

  test('navigates to Management → Magazine', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    // Navigate to Management tab
    await page.getByRole('button', { name: /Management/i }).click();

    // Click Magazine sub-tab
    await page.getByRole('button', { name: /Magazine/i }).click();

    await expect(page.getByText(/Magazin/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('lists stores', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/api\/stores.*/, {
      stores: [
        { id: 1, site_code: 'ST001', site_name: 'Magazin Central', firma: 'Firma 1', asm: 'ASM 1', regional: 'Regional 1' },
        { id: 2, site_code: 'ST002', site_name: 'Magazin Nord', firma: 'Firma 1', asm: 'ASM 2', regional: 'Regional 1' },
      ],
    });

    await page.goto('/');
    await expect(page.getByText('Hub')).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Management/i }).click();
    await page.getByRole('button', { name: /Magazine/i }).click();

    await expect(page.getByText('Magazin Central')).toBeVisible({ timeout: 10000 });
  });
});
