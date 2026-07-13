import { test, expect } from '@playwright/test';
import { setupBaseMocks } from './helpers';

test.describe('E2E: Management & Settings', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('navigates to Management tab and shows sub-tabs', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Management' }).first().click();

    await expect(page.getByRole('button', { name: 'Manageri', exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: 'Calculator Target' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Salarii' })).toBeVisible();
  });

  test('navigates to Setari tab and shows import section', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).first().click();

    await expect(page.getByText(/Import fișier vânzări/i)).toBeVisible({ timeout: 10000 });
  });
});
