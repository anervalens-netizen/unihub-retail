import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';

import { setupBaseMocks } from './helpers';


test.describe('E2E: accessibility smoke', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  for (const surface of ['Hub', 'Management'] as const) {
    test(`${surface} has no serious WCAG A/AA violations`, async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible();
      if (surface === 'Hub') {
        await expect(page.getByText('2026-05-06', { exact: true })).toBeVisible();
      } else {
        await page.getByRole('button', { name: 'Management' }).first().click();
        await expect(page.getByRole('tab', { name: 'Manageri', exact: true })).toBeVisible();
      }

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const seriousViolations = results.violations.filter(
        (violation) => violation.impact === 'critical' || violation.impact === 'serious',
      );

      expect(seriousViolations).toEqual([]);
    });
  }
});
