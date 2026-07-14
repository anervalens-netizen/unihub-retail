import { test, expect } from './fixtures';
import { setupBaseMocks } from './helpers';

test.describe('E2E: Login → Dashboard', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('renders dashboard after authenticated session', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: 'Focus' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Agenti' }).first()).toBeVisible();
  });

  test('shows dashboard summary data', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('150.000')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('200.000')).toBeVisible();
  });

  test('navigates to Focus tab', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Focus' }).first().click();
    await expect(page.getByText(/Focus & Campanii/i)).toBeVisible({ timeout: 5000 });
  });

  test('navigates to Management tab', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Management' }).first().click();
    await expect(page.getByRole('button', { name: 'Manageri', exact: true })).toBeVisible({ timeout: 5000 });
  });

  test('filter button is visible on Hub tab', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await expect(page.getByText('Filtre')).toBeVisible({ timeout: 5000 });
  });
});
