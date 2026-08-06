import { expect, test } from './fixtures';
import { setupBaseMocks } from './helpers';

test.describe('Insight contextual deep links', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('opens the requested Hub surface and persists its single-store context', async ({ page }) => {
    await page.goto(
      '/hub?source_context=insight&section=history&period=2026-05&firma=Firma%201&rm=Regional%201&magazin=S1&agent=Agent%201',
    );

    await expect(page.getByRole('tab', { name: 'Istoric' })).toHaveAttribute('aria-selected', 'true');
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('unihub_current_month')))
      .toBe('2026-05');
    await expect
      .poll(() =>
        page.evaluate(() => JSON.parse(localStorage.getItem('unihub_hub_filters') ?? '{}')),
      )
      .toEqual({
        firma: 'Firma 1',
        rm: 'Regional 1',
        magazin: 'S1',
        agent: 'Agent 1',
      });
  });

  test('opens the requested campaign mechanism', async ({ page }) => {
    await page.goto('/focus?source_context=insight&section=promo&period=2026-05');
    await expect(page.getByRole('tab', { name: 'Promo', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
