import { expect, test } from './fixtures';
import { setupBaseMocks } from './helpers';

test.beforeEach(async ({ context }) => setupBaseMocks(context));

test('primary navigation is reachable and activatable by keyboard', async ({ page }) => {
  await page.goto('/');
  const focus = page.getByRole('button', { name: 'Focus' }).first();
  await expect(focus).toBeVisible();
  await focus.focus();
  await expect(focus).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByText(/Focus & Campanii/i)).toBeVisible();
});
