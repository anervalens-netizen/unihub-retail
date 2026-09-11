import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { setupBaseMocks } from './helpers';

async function currentUrlState(page: Page) {
  return page.evaluate(() => ({
    pathname: window.location.pathname,
    params: Object.fromEntries(new URLSearchParams(window.location.search)),
  }));
}

test.describe('Insight contextual deep links', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('opens the requested Hub surface, preserves filters and canonicalizes live URL state', async ({ page }) => {
    await page.goto(
      '/hub?source_context=insight&section=history&period=2026-05&firma=Firma%201&rm=Regional%201&magazin=S1&agent=Agent%201',
    );

    await expect(page.getByRole('tab', { name: 'Istoric' })).toHaveAttribute('aria-selected', 'true');
    await expect
      .poll(() => page.evaluate(() => sessionStorage.getItem('unihub_current_month')))
      .toBe('2026-05');
    await expect
      .poll(() =>
        page.evaluate(() => JSON.parse(sessionStorage.getItem('unihub_hub_filters') ?? '{}')),
      )
      .toEqual({
        firma: 'Firma 1',
        rm: 'Regional 1',
        magazin: ['S1'],
        agent: ['Agent 1'],
      });
    await expect.poll(() => currentUrlState(page)).toEqual({
      pathname: '/hub',
      params: {
        source_context: 'retail',
        period: '2026-05',
        firma: 'Firma 1',
        rm: 'Regional 1',
        magazin: 'S1',
        agent: 'Agent 1',
        section: 'history',
      },
    });

    await page.locator('aside').getByRole('button', { name: 'Focus' }).click();
    await expect.poll(() => page.evaluate(() => window.location.pathname)).toBe('/focus');
    await expect.poll(() => new URL(page.url()).searchParams.get('source_context')).toBe('retail');
  });

  test('restores and updates the shared Focus section and campaign month across reload', async ({ page }) => {
    await page.goto('/focus?source_context=insight&section=promo&period=2026-04');
    await expect(page.getByRole('tab', { name: 'Promo', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    const periodSelect = page.locator('label').filter({ hasText: 'Perioada' }).locator('select');
    await expect(periodSelect).toHaveValue('2026-04');
    await expect.poll(() => new URL(page.url()).searchParams.get('source_context')).toBe('retail');
    await expect.poll(() => new URL(page.url()).searchParams.get('period')).toBe('2026-04');
    await expect.poll(() => new URL(page.url()).searchParams.get('section')).toBe('promo');

    await periodSelect.selectOption('2026-03');
    await expect.poll(() => new URL(page.url()).searchParams.get('period')).toBe('2026-03');
    await page.getByRole('tab', { name: 'Incentive', exact: true }).click();
    await expect.poll(() => new URL(page.url()).searchParams.get('section')).toBe('incentive');

    await page.reload();
    await expect(page.getByRole('tab', { name: 'Incentive', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(page.locator('label').filter({ hasText: 'Perioada' }).locator('select')).toHaveValue('2026-03');
  });
});
